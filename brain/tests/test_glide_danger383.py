"""Task 182 seq 383 (#448): SSBOT_FORUM_GLIDE_DANGER - with a hammer in sight a safe row whose first truly controllable key
opens the umbrella, or keeps a free float going when a release was possible, pays GLIDE_DANGER_C landed hits as its own
term of v2_nh. Everything else stays: raw nh, safe / sel / ok, the keys above v2_nh, an opening only later in the row
(recorded), a J the hold filter keeps, the Antic / Inflate / Deflate phases, true jumps, FORCED_RISK, no window, the
switch off. A prefix whose umbrella exit rests on a dash press (the model's unfixed dash cancel) makes the tick unknown:
no cost. The ticks are the real planner's (Forum v2 rows, the real rollout and hold filter); only the window signal comes
from a test tracker holding a Clapper's CC_SLAM unit (as tests/test_forced_slam309.py)."""
import math
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import forum_planner as fp, forum_v2 as v2
from ssbot.combat.forum_planner import ForumConfig, ForumPlanner
from ssbot.combat.holdfilter import hold_filter_jit
from ssbot.combat.planner import PlannerConfig
from ssbot.core.worldstate import E
from ssbot.knowledge import kinematics as kin
from tests.test_forced_slam309 import SLAM_IID, trk
from tests.test_forum_planner import FLOOR, _ctx, _prefs, _reed_forecaster, _world, arena, params  # noqa: F401
from tests.test_forum_v2 import _support_with
from tests.test_glide_jump_hold380 import X, _glide_masks, _j_held, _state

J, D = kin.B_JUMP, kin.B_DASH


def _forecast(units=True, blocks=(), reed_x=30.0):
    ls = _support_with(list(blocks))
    ls.trk = trk((SLAM_IID, v2.CLAPPER, NS(fam="CC_SLAM") if units else None))
    ls.pend = []
    return v2.V2Forecast(_reed_forecaster(None, x=reed_x).forecast(0.8), ls)


def _tick(params, arena, start, prefix, hold, *, units=True, blocks=(), reed_x=30.0):
    """One real Forum v2 tick; the tracker holds the Clapper's CC_SLAM unit when units (the window)."""
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                      ForumConfig(deadline_ms=math.inf, esc_deadline_ms=math.inf, v2=True, forced_rank="seen_cf"),
                      crest="Wanderer")
    pl.debug = True
    x, y = float(start[kin.PX, 0]), float(start[kin.PY, 0])
    f = _forecast(units, blocks, reed_x)
    ws = _world(x)
    ws.hero.pos = E((x, y))
    ws.stamp.frame = 100
    res = pl.tick(ws, start, hold, np.asarray(prefix, np.int64), f, _prefs(None, x), _ctx())
    return pl, res


def _both(params, arena, monkeypatch, start, prefix, hold, **kw):
    out = []
    for on in (False, True):
        monkeypatch.setattr(fp, "GLIDE_DANGER", on)
        out.append(_tick(params, arena, start, prefix, hold, **kw))
    return out


def _rows(pl):
    """The tick's rows: requested first key, latched first key, the rollout's modes (the planner's own debug copy)."""
    s, d = pl.last_sel, pl.last_info["dbg"]
    P = int(d["P"])
    md = np.asarray(d["mode"])
    return s, P, md


def _same_but_v2nh(a, b):
    sa, sb = a.last_sel, b.last_sel
    for k in ("nh", "safe", "allowed", "S", "hz", "U", "keep", "mkeep", "sel", "forced"):
        assert np.array_equal(np.asarray(sa[k]), np.asarray(sb[k])), k
    return np.asarray(sb["v2_nh"], float) - np.asarray(sa["v2_nh"], float)


def test_a_first_key_that_opens_the_umbrella_pays_once_on_v2_nh(params, arena, monkeypatch):
    """In the air out of the umbrella (a jump whose J was let go): a J on the first new mask opens it in that step."""
    s = _state(params, arena, [J] * 12 + [0] * 4)
    assert s[kin.MODE, 0] != kin.M_GLIDE and s[kin.GROUND, 0] <= 0
    (p0, r0), (p1, r1) = _both(params, arena, monkeypatch, s, [0], kin.HoldState.idle(1))
    assert "glide_danger" not in p0.last_info and p0.audit.gd_ticks == 0
    dv = _same_but_v2nh(p0, p1)
    s1, P, md = _rows(p1)
    req = (np.asarray(s1["cmd"])[:, 0] & J) != 0
    opens = req & (md[:, P] != kin.M_GLIDE) & (md[:, P + 1] == kin.M_GLIDE)
    safe = np.asarray(s1["safe"])
    assert (opens & safe).any()
    assert np.array_equal(dv, np.where(opens & safe, fp.GLIDE_DANGER_C, 0.0))     # exactly once, safe openers only
    note = p1.last_info["glide_danger"]
    assert note["window"] == [SLAM_IID] and note["mode"] != kin.M_GLIDE
    assert note["opens"] == int((opens & safe).sum()) == note["charged"] and note["floats"] == 0
    assert note["chosen"]["row"] == r1.idx and note["chosen"]["cost"] == float(dv[r1.idx])
    assert p1.audit.gd_ticks == 1 and p1.audit.gd_rows == note["charged"]


def test_an_opening_only_later_in_the_row_is_recorded_not_charged(params, arena, monkeypatch):
    s = _state(params, arena, [J] * 12 + [0] * 4)
    (p0, _), (p1, _) = _both(params, arena, monkeypatch, s, [0], kin.HoldState.idle(1))
    dv = _same_but_v2nh(p0, p1)
    s1, P, md = _rows(p1)
    later = (md[:, P + 1] != kin.M_GLIDE) & (md[:, P + 2:] == kin.M_GLIDE).any(axis=1) & np.asarray(s1["safe"])
    assert later.any() and (dv[later] == 0).all()
    assert p1.last_info["glide_danger"]["later"] == int(later.sum())


def test_a_free_float_kept_pays_and_a_release_does_not(params, arena, monkeypatch):
    """Floating (Float Idle) with J held long and in flight: the first new key keeps J or lets it go."""
    s = _state(params, arena, _glide_masks(params, arena)[0])
    assert s[kin.MODE, 0] == kin.M_GLIDE
    (p0, _), (p1, r1) = _both(params, arena, monkeypatch, s, [J], _j_held(47))
    dv = _same_but_v2nh(p0, p1)
    note = p1.last_info["glide_danger"]
    assert note["mode"] == kin.M_GLIDE and note["phase"] == 2.0
    s1, P, md = _rows(p1)
    cmd0 = np.asarray(s1["cmd"])[:, 0]
    full = np.concatenate([np.full((len(cmd0), P), J, np.int64), np.asarray(s1["cmd"], np.int64)], axis=1)
    lat, _ = hold_filter_jit(full, _j_held(47))
    held = ((cmd0 & J) != 0) & ((lat[:, P] & J) != 0) & ((lat[:, P] & D) == 0) & np.asarray(s1["safe"])
    keep = held & (md[:, P + 1] == kin.M_GLIDE)            # the rollout's next state still floats: charged
    leave = held & (md[:, P + 1] != kin.M_GLIDE)           # J kept but the first key leaves it (an attack's new edge)
    release = ((lat[:, P] & J) == 0) & np.asarray(s1["safe"])
    assert keep.any() and release.any()
    assert (dv[keep] == fp.GLIDE_DANGER_C).all() and (dv[release] == 0).all() and (dv[leave] == 0).all()
    assert note["floats"] == int(keep.sum()) and note["opens"] == 0


ROW = "JUMP(24)R+runR16_attack"           # the library row: J held, R; J+A at 20 - 22 (A's new edge at 20)
A = kin.B_ATTACK


def _only(name):
    real = fp.veto

    def veto(cs, ctx):
        ok, why = real(cs, ctx)
        return ok & np.array([cs.name(i) == name for i in range(len(cs.cmd))]), why
    return veto


def _continue_tick(params, arena, monkeypatch, on, held_a):
    """Two real ticks: at frame 100 in a steady float the planner takes ROW; at 120 its CONTINUE's first new key is ROW's
    command 20 (J+A). held_a: A already held (the state's previous mask and the filter latched it long ago, the in-flight
    key holds it too), so 20 is no new A edge."""
    s1 = _state(params, arena, _glide_masks(params, arena)[0])
    monkeypatch.setattr(fp, "GLIDE_DANGER", on)
    pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                      ForumConfig(deadline_ms=math.inf, esc_deadline_ms=math.inf, v2=True, forced_rank="seen_cf"),
                      crest="Wanderer")
    pl.debug = True
    f = _forecast()

    def tick(s, frame, prefix, hold):
        x, y = float(s[kin.PX, 0]), float(s[kin.PY, 0])
        ws = _world(x)
        ws.hero.pos = E((x, y))
        ws.stamp.frame = frame
        return pl.tick(ws, s, hold, np.asarray(prefix, np.int64), f, _prefs(None, x), _ctx())

    monkeypatch.setattr(fp, "veto", _only(ROW))
    r1 = tick(s1, 100, [J], _j_held(47))
    assert r1.name == ROW and int(r1.cmd[20]) == J | A and int(r1.cmd[19]) & A == 0
    monkeypatch.undo()                                     # the real veto again (and the switch, set below)
    monkeypatch.setattr(fp, "GLIDE_DANGER", on)
    masks = np.concatenate([[J], np.asarray(r1.cmd[:19], np.int64)])[None]
    lat, hold2 = hold_filter_jit(masks, _j_held(47))
    s2 = kin.rollout(s1, lat, params, arena).final[:, :1].copy()
    assert s2[kin.MODE, 0] == kin.M_GLIDE and s2[kin.PHASE, 0] == 2.0      # still the steady float at 120
    prefix2 = [int(r1.cmd[19])]
    if held_a:
        s2[kin.PREV, 0] = float(int(s2[kin.PREV, 0]) | A)
        hold2 = kin.HoldState(hold2.latched.copy(), hold2.desired.copy(), hold2.pending.copy(), hold2.age.copy())
        hold2.latched[0, 1] = hold2.desired[0, 1] = True
        hold2.pending[0, 1] = 0
        hold2.age[0, 1] = 60
        prefix2 = [int(r1.cmd[19]) | A]
    tick(s2, 120, prefix2, hold2)
    return pl


@pytest.mark.parametrize("held_a", [False, True])
def test_a_continue_whose_first_key_is_a_new_attack_leaves_the_float_and_pays_nothing(params, arena, monkeypatch,
                                                                                    held_a):
    """Sol seq384: the CONTINUE of JUMP(24)R+runR16_attack 20 frames on, its first new key J+A. A new A edge in the steady
    float is kin_jit's Attack Cancel (out of GLIDE on the next state): no float kept, no cost. A held long before (no new
    edge): the float goes on with J kept while a release was possible - charged as before."""
    p0 = _continue_tick(params, arena, monkeypatch, False, held_a)
    p1 = _continue_tick(params, arena, monkeypatch, True, held_a)
    dv = _same_but_v2nh(p0, p1)
    s1, P, md = _rows(p1)
    c = len(np.asarray(s1["cmd"])) - 1                     # the CONTINUE row (the last)
    assert int(np.asarray(s1["cmd"])[c, 0]) == J | A and np.asarray(s1["safe"])[c]
    note = p1.last_info["glide_danger"]
    assert note["mode"] == kin.M_GLIDE and note["phase"] == 2.0
    if held_a:
        assert md[c, P + 1] == kin.M_GLIDE and dv[c] == fp.GLIDE_DANGER_C
    else:
        assert md[c, P + 1] != kin.M_GLIDE and dv[c] == 0.0


def test_true_jumps_from_the_floor_pay_nothing(params, arena, monkeypatch):
    s = np.asarray(kin.initial_state(params, X, FLOOR + params.foot), float).reshape(kin.K, 1)
    (p0, r0), (p1, r1) = _both(params, arena, monkeypatch, s, [0], kin.HoldState.idle(1))
    dv = _same_but_v2nh(p0, p1)
    s1, P, md = _rows(p1)
    assert ((np.asarray(s1["cmd"])[:, 0] & J) != 0).any()                 # jump rows are there
    assert not dv.any() and p1.last_info["glide_danger"]["charged"] == 0
    assert (r0.name, int(r0.mask)) == (r1.name, int(r1.mask))


def test_a_jump_after_the_prefix_landed_her_pays_nothing(params, arena, monkeypatch):
    s = _state(params, arena, _glide_masks(params, arena)[1])
    assert s[kin.MODE, 0] == kin.M_GLIDE
    (p0, _), (p1, _) = _both(params, arena, monkeypatch, s, [0, 0, 0], _j_held(47))
    note = p1.last_info["glide_danger"]
    assert note["mode"] != kin.M_GLIDE and "unknown" not in note                # landed in the prefix (a reliable exit)
    assert not _same_but_v2nh(p0, p1).any() and note["charged"] == 0


def test_a_j_the_filter_keeps_and_the_antic_it_opened_pay_nothing(params, arena, monkeypatch):
    """The prefix's own J opens the umbrella (Antic at P) and the filter's minimum press keeps J on every row."""
    s = _state(params, arena, [J] * 12 + [0] * 4)
    (p0, _), (p1, _) = _both(params, arena, monkeypatch, s, [J], kin.HoldState.idle(1))
    note = p1.last_info["glide_danger"]
    assert note["mode"] == kin.M_GLIDE and note["phase"] == 0.0
    assert note["forced_j"] > 0 and note["charged"] == 0 and not _same_but_v2nh(p0, p1).any()


def test_the_deflate_pays_nothing_even_with_j_kept(params, arena, monkeypatch):
    high = _glide_masks(params, arena)[0]
    s = _state(params, arena, high + [0])                                   # one frame let go in the float: Deflate
    assert s[kin.MODE, 0] == kin.M_GLIDE and s[kin.PHASE, 0] == 3.0
    (p0, _), (p1, _) = _both(params, arena, monkeypatch, s, [0, 0], kin.HoldState.idle(1))
    note = p1.last_info["glide_danger"]
    assert note["mode"] == kin.M_GLIDE and note["phase"] == 3.0
    assert note["charged"] == 0 and not _same_but_v2nh(p0, p1).any()


def test_a_prefix_that_leaves_the_umbrella_on_a_dash_is_unknown(params, arena, monkeypatch):
    s = _state(params, arena, _glide_masks(params, arena)[0])
    r = kin.rollout(s, np.asarray([[J | D] + [J] * 4], np.int64), params, arena)
    assert r.mode[0, 0] == kin.M_GLIDE and r.mode[0, 1] != kin.M_GLIDE     # the model's dash cancel in the prefix
    # the real tick: the dash locks every row (FORCED_RISK, no safe row), so no cost and the old choice
    (p0, r0), (p1, r1) = _both(params, arena, monkeypatch, s, [J | D], _j_held(47))
    assert p1.last_sel["forced"] and "glide_danger" not in p1.last_info
    assert (r0.name, int(r0.mask), r0.idx) == (r1.name, int(r1.mask), r1.idx)
    # the class on this tick's own rows (the real hold filter and rollout), every row taken as safe: unknown, no cost
    cmd = np.asarray(p1.last_sel["cmd"], np.int64)
    full = np.concatenate([np.full((len(cmd), 1), J | D, np.int64), cmd], axis=1)
    lat, _ = hold_filter_jit(full, _j_held(47))
    ro = kin.rollout(s, lat, params, arena)
    pl = NS(audit=fp.EnvelopeAudit())
    cost, note = fp._glide_danger_cost(pl, _forecast(), s, 1, full, lat, ro, np.ones(len(cmd), bool), params, arena)
    assert cost is None and note["unknown"] == "the prefix left the umbrella on a dash" and "charged" not in note
    assert pl.audit.gd_unknown == 1 and pl._gd_rows is None


def test_no_hammer_in_sight_no_cost(params, arena, monkeypatch):
    s = _state(params, arena, [J] * 12 + [0] * 4)
    (p0, r0), (p1, r1) = _both(params, arena, monkeypatch, s, [0], kin.HoldState.idle(1), units=False)
    assert "glide_danger" not in p1.last_info and p1.audit.gd_ticks == 0
    assert not _same_but_v2nh(p0, p1).any() and (r0.name, int(r0.mask)) == (r1.name, int(r1.mask))


def test_forced_risk_is_untouched(params, arena, monkeypatch):
    """Every row in contact (FORCED_RISK): no safe row, no cost, the same choice."""
    s = _state(params, arena, [J] * 12 + [0] * 4)
    (p0, r0), (p1, r1) = _both(params, arena, monkeypatch, s, [0], kin.HoldState.idle(1),
                               blocks=[(0.0, 0.0, 60.0, 30.0)])
    assert p1.last_sel["forced"] and "glide_danger" not in p1.last_info
    assert (r0.name, int(r0.mask), r0.idx) == (r1.name, int(r1.mask), r1.idx)


@pytest.mark.parametrize("gjh", [False, True])
def test_the_jump_hold_fix_reads_the_same_with_the_cost_on(params, arena, monkeypatch, gjh):
    """In the float with an old hold: GJH's tick start (cleared / glide) is the same with or without the cost."""
    monkeypatch.setattr(fp, "GLIDE_JUMP_HOLD", gjh)
    s = _state(params, arena, _glide_masks(params, arena)[0])
    notes = []
    for on in (False, True):
        monkeypatch.setattr(fp, "GLIDE_DANGER", on)
        pl = ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                          ForumConfig(deadline_ms=math.inf, esc_deadline_ms=math.inf, v2=True, forced_rank="seen_cf"),
                          crest="Wanderer")
        pl.jump_until = pl.ticks + 20
        ls = _support_with([])
        ls.trk = trk((SLAM_IID, v2.CLAPPER, NS(fam="CC_SLAM")))
        ls.pend = []
        f = v2.V2Forecast(_reed_forecaster(None, x=30.0).forecast(0.8), ls)
        x, y = float(s[kin.PX, 0]), float(s[kin.PY, 0])
        ws = _world(x)
        ws.hero.pos = E((x, y))
        ws.stamp.frame = 100
        pl.tick(ws, s, _j_held(47), np.asarray([J], np.int64), f, _prefs(None, x), _ctx())
        g = pl.last_info.get("glide_hold")
        notes.append(None if g is None else (g["glide"], g["cleared"]))
    assert notes[0] == notes[1]
    assert (notes[0] == (True, 20)) if gjh else notes[0] is None
