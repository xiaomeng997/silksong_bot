"""Task 1v1 G3: the Forum planner's delayed / chained down slashes (combat.dslash, SSBOT_FORUM_DSLASH) and the
certain-hit rule for them."""
import math
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import dslash
from ssbot.combat import forum_v2 as v2
from ssbot.combat.forum_planner import ForumConfig, ForumPlanner
from ssbot.combat.planner import PlannerConfig
from ssbot.knowledge import kinematics as kin
from tests.test_forum_planner import FLOOR, _ctx, _prefs, _reed_forecaster, _world, arena  # noqa: F401
from tests.test_special_mode import _support

RX = 37.0                         # the Reed (the test's target): body 36.5 .. 37.5, FLOOR .. FLOOR + 2


@pytest.fixture(scope="module")
def params():
    from ssbot.train.forum_planner_policy import CREST_PARAMS
    return kin.HeroParams.load(CREST_PARAMS["Wanderer"])


def _rising(x: np.ndarray) -> np.ndarray:
    on = x != 0
    return np.flatnonzero(on & ~np.concatenate([[False], on[:-1]]))


def test_templates_one_jump_press_one_strike_and_in_place_rows():
    M, pj, names = dslash.templates("ground")
    assert len(M) == len(dslash.GROUND_HOLDS) * len(dslash.GROUND_PRESS) * 3 == 132
    for m, p in zip(M, pj):
        assert list(_rising(m & kin.B_JUMP)) == [0]                     # jump now, once
        assert list(_rising(m & kin.B_ATTACK)) == [p]
        assert (m[p - 1:p + 5] & kin.B_DOWN).all()
    A, pa, na = dslash.templates("air")
    assert len(A) == len(dslash.AIR_W) * 3
    inplace = [m for m, n in zip(A, na) if n.endswith("N")]
    assert inplace and all(((m & (kin.B_LEFT | kin.B_RIGHT)) == 0).all() for m in inplace)   # no side key
    assert not (A & kin.B_JUMP).any()
    J, _, _ = dslash.templates("air", jump_rem=5)                       # a committed jump hold is kept
    assert (J[:, :5] & kin.B_JUMP).all() and not (J[:, 5:] & kin.B_JUMP).any()


def test_chain_has_no_jump_press_in_the_air():
    M, pj, names = dslash.templates("ground")
    X, xp, xn = dslash.expand(M[:1], pj[:1], names[:1], 36)
    c = dslash.chain(X[0], int(xp[0]) + 30, 60)
    assert list(_rising(c & kin.B_JUMP)) == [0]                         # only the take-off
    assert list(_rising(c & kin.B_ATTACK)) == [int(xp[0]), int(xp[0]) + 30]


class _Tab:
    """A range table whose RE_STAB template moves the body by `v` u a frame (0: the body stays where it is)."""
    def __init__(self, v=0.0):
        self.v = v
        self.spec = NS(branches={"RE_STAB": ("main",)})
        self.templates = {("RE_STAB", "main"): object()}

    def position(self, tp, b, anchor, s, hero_du, fam):
        return (anchor[0] + s * self.v * b, anchor[1])


def _tick(params, arena, parts, in_move=True, hx=34.0, monkeypatch=None, cert=True, prev=None, v=0.0):
    from ssbot.combat import stance_block
    monkeypatch.setattr(stance_block, "blocked", lambda *a, **k: None)      # the Reed never guards here
    monkeypatch.setattr(v2.RangeSupport, "reaction", lambda self, *a, **k: None)   # nor counters a hit
    monkeypatch.setattr(dslash, "DSLASH", True)
    monkeypatch.setattr(dslash, "CERT", cert)
    inst = NS(fam="RE_STAB", branch=None, t0=0.0, x0=RX, y0=FLOOR + 1.0, s=-1, hero_du=0.0) if in_move else None
    trk = NS(now={7: ("Song Reed", {"pos": (RX, FLOOR + 1.0), "type_key": "Song Reed"}, inst)},
             tables={"Song Reed": _Tab(v)}, hero=None, T=0.0)
    rs = _support(parts, trk)
    inner = _reed_forecaster(None, x=RX).forecast(0.8)
    f = v2.V2Forecast(inner, rs)
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                      ForumConfig(deadline_ms=math.inf, esc_deadline_ms=math.inf, v2=True), crest="Wanderer")
    pl.debug = True
    start = kin.initial_state(params, hx, FLOOR + params.foot)
    r = pl.tick(_world(hx), start, kin.HoldState.idle(1), np.zeros(1, np.int64), f, _prefs(None, hx), _ctx())
    return pl, r


# the floor around the Reed is dangerous (a hazard on the ground): a down slash that misses lands in it
FLOOR_HAZARD = {9: [(35.6, FLOOR, 38.4, FLOOR + 0.6)]}


def test_on_family_rows(params, arena, monkeypatch):
    pl, r = _tick(params, arena, FLOOR_HAZARD, monkeypatch=monkeypatch)
    assert pl.audit.ds_ticks == 1 and pl.audit.ds_rows > 0
    assert any(n.startswith("DS ") for n in pl.last_info["dbg"]["names"])


def test_family_off_adds_nothing(params, arena, monkeypatch):
    monkeypatch.setattr(dslash, "DSLASH", False)
    trk = NS(now={}, tables={}, hero=None, T=0.0)
    rs = _support(FLOOR_HAZARD, trk)
    f = v2.V2Forecast(_reed_forecaster(None, x=RX).forecast(0.8), rs)
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                      ForumConfig(deadline_ms=math.inf, esc_deadline_ms=math.inf, v2=True), crest="Wanderer")
    pl.debug = True
    start = kin.initial_state(params, 34.0, FLOOR + params.foot)
    pl.tick(_world(34.0), start, kin.HoldState.idle(1), np.zeros(1, np.int64), f, _prefs(None, 34.0), _ctx())
    assert pl.audit.ds_ticks == 0 and not any(n.startswith("DS ") for n in pl.last_info["dbg"]["names"])


def test_jump_and_delayed_strike_is_one_row_that_hits(params, arena, monkeypatch):
    pl, r = _tick(params, arena, {}, monkeypatch=monkeypatch)
    ds, D0 = pl._ds, pl._ds_D0
    assert ds is not None and len(ds.cmd)
    assert pl.audit.ds_pass < pl.audit.ds_tpl                        # the prefilter drops templates
    nh = np.asarray(pl.last_sel["nh"])
    ground = [q for q, n in enumerate(ds.names) if n.startswith("DS j")]
    assert ground and all(nh[D0 + q] >= 1 for q in ground)            # the strike is counted on the jump's row
    # certain (the Reed in a move, contact robust): the planner lane is the bounce lane (EV_POGO at the contact)
    assert ds.cert.any()
    q = int(np.flatnonzero(ds.cert)[0])
    assert ds.ev[q, ds.c1[q]] & kin.EV_POGO


def test_idle_target_is_not_certain(params, arena, monkeypatch):
    pl, r = _tick(params, arena, {}, in_move=False, monkeypatch=monkeypatch)
    assert pl._ds is not None and not pl._ds.cert.any() and (pl._ds.c2 < 0).all()


def test_certain_rows_skip_the_miss_branch(params, arena, monkeypatch):
    pl, r = _tick(params, arena, FLOOR_HAZARD, monkeypatch=monkeypatch, cert=True)
    ds, D0 = pl._ds, pl._ds_D0
    safe = np.asarray(pl.last_sel["safe"])
    n_cert_safe = int(safe[D0 + np.flatnonzero(ds.cert)].sum())
    pl2, r2 = _tick(params, arena, FLOOR_HAZARD, monkeypatch=monkeypatch, cert=False)
    ds2, D02 = pl2._ds, pl2._ds_D0
    safe2 = np.asarray(pl2.last_sel["safe"])
    assert not ds2.cert.any()
    assert n_cert_safe > 0                                            # the bounce lane clears the hazard
    # the same rows on both branches: the miss lane lands in the hazard
    same = [D02 + q for q, n in enumerate(ds2.names) if n in set(np.array(ds.names)[ds.cert])]
    assert same and int(safe2[same].sum()) < n_cert_safe


def test_second_strike_counts(params, arena, monkeypatch):
    pl, r = _tick(params, arena, {}, monkeypatch=monkeypatch)
    ds, D0 = pl._ds, pl._ds_D0
    ch = np.flatnonzero(ds.c2 >= 0)
    assert len(ch)
    nh = np.asarray(pl.last_sel["nh"])
    T1 = 1 + 36 + 1
    for q in ch:
        assert nh[D0 + q] >= 2 or (ds.extra[q] == 1 and ds.c2[q] >= T1)
        # the second press comes with no jump press after the take-off
        assert len(_rising(np.asarray(ds.ext[q]) & kin.B_JUMP)) <= 1


def test_special_fast_rolls_the_whole_set_only_every_few_ticks(params, arena, monkeypatch):
    """SSBOT_FORUM_SPECIAL_FAST (G3 item 3): the move's first tick rolls every template, the next ones only those that
    start now; the BOARD keeps the full tick's strike spot."""
    from ssbot.combat import special_mode as sm
    from tests.test_special_mode import _clapper, _planner, _trk
    monkeypatch.setattr(sm, "SPECIAL_MODE", True)
    monkeypatch.setattr(sm, "LONG", True)
    monkeypatch.setattr(sm, "FAST", True)
    monkeypatch.setattr(sm, "FULL_EVERY", 6)
    sm.BOARD.clear()
    trk = _trk({7: _clapper(30.0, 1, 20)})
    rs = _support({7: [(32.3, FLOOR, 40.0, FLOOR + 7.0)]}, trk)
    f = v2.V2Forecast(_reed_forecaster(None, x=46.0).forecast(0.8), rs)
    pl = _planner(params, arena)
    start = kin.initial_state(params, 34.0, FLOOR + params.foot)
    tried = []
    for _ in range(3):
        pl.tick(_world(34.0), start, kin.HoldState.idle(1), np.zeros(1, np.int64), f, _prefs(None, 34.0), _ctx())
        tried.append(pl.spec_n[1])
    assert pl.audit.sm_full_ticks == 1
    assert tried[1] < tried[0] / 3 and tried[2] == tried[1]
    sm.BOARD.clear()


@pytest.mark.parametrize("hold", [False, True])
def test_special_rows_keep_a_committed_jump_hold(params, arena, monkeypatch, hold):
    """SSBOT_FORUM_SPECIAL_HOLD (G3 item 4): with a jump hold committed, the special rows hold the jump over its
    remaining frames (else the selection's `keep` key ranks every one of them behind the rows that do)."""
    from ssbot.combat import special_mode as sm
    from tests.test_special_mode import _clapper, _planner, _trk
    monkeypatch.setattr(sm, "SPECIAL_MODE", True)
    monkeypatch.setattr(sm, "LONG", True)
    monkeypatch.setattr(sm, "HOLD", hold)
    sm.BOARD.clear()
    trk = _trk({7: _clapper(30.0, 1, 20)})
    rs = _support({7: [(32.3, FLOOR, 40.0, FLOOR + 7.0)]}, trk)
    f = v2.V2Forecast(_reed_forecaster(None, x=46.0).forecast(0.8), rs)
    pl = _planner(params, arena)
    pl.debug = True
    pl.jump_until = pl.ticks + 5
    start = kin.initial_state(params, 34.0, FLOOR + params.foot)
    pl.tick(_world(34.0), start, kin.HoldState.idle(1), np.zeros(1, np.int64), f, _prefs(None, 34.0), _ctx())
    names = pl.last_info["dbg"]["names"]
    sp = [i for i, n in enumerate(names) if n.startswith("SPECIAL")]
    assert sp
    held = (np.asarray(pl.last_sel["cmd"])[sp, :5] & kin.B_JUMP != 0).all(axis=1)
    assert held.all() if hold else not held.all()
    sm.BOARD.clear()


def test_a_lunging_body_is_not_a_certain_hit(params, arena):
    """The certain-hit rule's lunge-phase variant: a contact found only because the predicted body moves on at its
    present velocity (it may stop any frame) is not robust; the same contact on a standing body is."""
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2), ForumConfig(v2=True), crest="Wanderer")
    M, pj, names = dslash.templates("ground")
    q = names.index("DS j20p18R")
    from ssbot.combat.holdfilter import hold_filter_jit
    lat, _ = hold_filter_jit(np.concatenate([np.zeros((1, 1), np.int64), M[q:q + 1]], axis=1), kin.HoldState.idle(1))
    start = kin.initial_state(params, 34.0, FLOOR + params.foot)
    r = kin.rollout(start, lat, params, arena)
    T1 = r.flags.shape[1]
    t = np.arange(T1) * params.frame_time
    k, j, _, _ = pl._ds_hits(r, lat, 1, np.array([[[36.0, FLOOR, 37.0, FLOOR + 5.0]] * T1]), np.ones((1, T1), bool),
                             np.ones(1, bool), np.array([2]), 0.0, dslash.CERT_SHIFTS)
    jc = int(j[0])
    assert jc > 0
    x0 = 36.0 - 10.0 * t[jc]                      # a body running at 10 u/s that reaches the strike at frame jc
    mov = np.stack([x0 + 10.0 * t, np.full(T1, FLOOR), x0 + 1.0 + 10.0 * t, np.full(T1, FLOOR + 5.0)], axis=1)[None]
    _, j2, _, rob2 = pl._ds_hits(r, lat, 1, mov, np.ones((1, T1), bool), np.ones(1, bool), np.array([2]), 0.0,
                                 dslash.CERT_SHIFTS, stop=True)
    _, _, _, rob1 = pl._ds_hits(r, lat, 1, np.array([[[36.0, FLOOR, 37.0, FLOOR + 5.0]] * T1]),
                                np.ones((1, T1), bool), np.ones(1, bool), np.array([2]), 0.0, dslash.CERT_SHIFTS,
                                stop=True)
    assert j2[0] >= 0 and not rob2[0] and rob1[0]


def test_a_strike_on_a_moving_move_is_not_certain(params, arena, monkeypatch):
    """The certain-hit rule reads the move's own body path (its template's displacement): the scorer's body stands
    still here, the move carries it away at 60 u/s, so no strike on it is certain."""
    pl, r = _tick(params, arena, {}, monkeypatch=monkeypatch, v=1.0)
    assert pl._ds is not None and len(pl._ds.cmd) and not pl._ds.cert.any()
