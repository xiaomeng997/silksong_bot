"""Task 182 seq 380 (#444): SSBOT_FORUM_GLIDE_JUMP_HOLD - the committed jump hold (jump_until) and the umbrella.

The hold keeps a pressed jump's rise (DESIGN 3.5.4); in the umbrella (GLIDE) J is the float. With the switch on, a tick that
begins in the umbrella ends the old hold before any row is built or reads it (ForumPlanner.tick ->
_glide_hold_tick_start), so it neither binds that tick nor comes back when she leaves the umbrella; a chosen J that finds her
still in the umbrella after the prefix, or opens one, commits no hold (_glide_press on the planner's own rollout); a jump -
also one pressed after the prefix left the umbrella - commits its hold as before. Off: the hold as in 8e34fb6c. The states
come from the real rollout (kin_jit's glide, landing and start_glide), the ticks from the real planner."""
import math
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import forum_planner as fp
from ssbot.combat.forum_planner import EnvelopeAudit, ForumConfig, ForumPlanner
from ssbot.combat.planner import PlannerConfig
from ssbot.core.worldstate import E
from ssbot.knowledge import kinematics as kin
from tests.test_forum_planner import FLOOR, _ctx, _prefs, _reed_forecaster, _world, arena, params  # noqa: F401

J = kin.B_JUMP
X = 20.0                                          # 10 u left of the idle Reed, 6 u right of the left wall


def _ws(frame):
    return NS(stamp=NS(frame=frame))


def _roll(params, arena, masks, x=X):
    S = kin.initial_state(params, x, FLOOR + params.foot)
    return kin.rollout(S, np.asarray(masks, np.int64)[None], params, arena)


def _state(params, arena, masks, x=X):
    """The real state after `masks` from standing at x ([K, 1], the production shape)."""
    return _roll(params, arena, masks, x).final[:, :1].copy()


def _glide_masks(params, arena):
    """Jump, release, press again and hold: the umbrella opens (the rollout's own glide). Returns the masks to a high
    Float and to 2 frames above the landing (still in the umbrella)."""
    m = [J] * 12 + [0] * 4 + [J] * 160
    r = _roll(params, arena, m)
    md = r.mode[0]
    g = np.flatnonzero(md == kin.M_GLIDE)
    assert len(g) > 60
    land = int(g[0] + np.argmax(md[g[0]:] != kin.M_GLIDE))          # the first state out of the umbrella: landed
    assert land > g[0] + 40 and (r.vel[0, land - 6:land, 1] < 0).all()
    return m[:g[0] + 30], m[:land - 2]


def _real(params, arena):
    return ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"),
                        ForumConfig(deadline_ms=math.inf))


def _tick(pl, start, frame, prefix, hold):
    x, y = float(start[kin.PX, 0]), float(start[kin.PY, 0])
    ws = _world(x)
    ws.hero.pos = E((x, y))
    ws.stamp.frame = frame
    f = _reed_forecaster(None, x=30.0).forecast(0.8)
    return pl.tick(ws, start, hold, np.asarray(prefix, np.int64), f, _prefs(None, x), _ctx(kill_hp=5.0))


def _j_held(age):
    return kin.HoldState.from_hf({"latched": int(J), "desired": int(J), "age": {0: age}})


def _first_key(has_j):
    """A test-only restriction of the planner's own rows: those whose first new key does (not) hold J."""
    real = fp.veto

    def veto(cs, ctx):
        ok, why = real(cs, ctx)
        jf = (np.asarray(cs.cmd)[:, 0] & J) != 0
        return ok & (jf if has_j else ~jf), why
    return veto


# ---- the lifecycle at the start of a tick (ForumPlanner.tick, before any row) --------------------------------------------

def _stub(seen, jump_until=30):
    def ordinary_tick(*a, **k):
        seen.append(p.jump_until)                 # what every row builder / reader of this tick would see
        p.ticks += 1
        return NS(t_ms={}, mask=0)
    p = NS(chain_native=None, ticks=10, jump_until=jump_until, macro_until=-1, _clock_d=None, audit=EnvelopeAudit(),
           _ordinary_tick=ordinary_tick, measurement_enabled=False, prev_cmd=None)
    return p


def _mode(m):
    s = np.zeros((kin.K, 1))
    s[kin.MODE, 0] = m
    return s


def test_an_observed_umbrella_ends_the_hold_before_any_row_and_it_does_not_come_back(monkeypatch):
    monkeypatch.setattr(fp, "GLIDE_JUMP_HOLD", True)
    seen = []
    p = _stub(seen)
    ForumPlanner.tick(p, _ws(100), _mode(kin.M_GLIDE), None, np.zeros(1, np.int64), None, None, None)
    assert seen == [-1] and p.jump_until == -1
    assert p._glide_hold_note == {"glide": True, "cleared": 20}
    assert (p.audit.glide_ticks, p.audit.glide_hold_cleared) == (1, 1)
    ForumPlanner.tick(p, _ws(101), _mode(0), None, np.zeros(1, np.int64), None, None, None)     # out of the umbrella
    assert seen == [-1, -1] and p._glide_hold_note is None                                         # nothing revived


def test_outside_the_umbrella_and_with_the_switch_off_the_hold_is_untouched(monkeypatch):
    monkeypatch.setattr(fp, "GLIDE_JUMP_HOLD", True)
    seen = []
    p = _stub(seen)
    ForumPlanner.tick(p, _ws(100), _mode(kin.M_SPRINT), None, np.zeros(1, np.int64), None, None, None)
    assert seen == [30] and p.audit.glide_ticks == 0
    monkeypatch.setattr(fp, "GLIDE_JUMP_HOLD", False)
    seen = []
    p = _stub(seen)
    ForumPlanner.tick(p, _ws(100), _mode(kin.M_GLIDE), None, np.zeros(1, np.int64), None, None, None)
    assert seen == [30] and not hasattr(p, "_glide_hold_note")


# ---- the press on the planner's own rollout (real states, real kin_jit) ------------------------------------------------

def test_the_press_reads_the_rollout_before_and_after_the_first_new_mask(params, arena):
    high, low = _glide_masks(params, arena)
    # still in the umbrella after the prefix: J only keeps the float
    s = _state(params, arena, high)
    assert s[kin.MODE, 0] == kin.M_GLIDE
    r = kin.rollout(s, np.asarray([[J] * 8], np.int64), params, arena)
    assert fp._glide_press(r.mode, 0, 1, kin.M_GLIDE) == "in"
    # a press in the air after a jump whose J was let go: start_glide in the press's own step
    s = _state(params, arena, [J] * 12 + [0] * 4)
    assert s[kin.MODE, 0] != kin.M_GLIDE and s[kin.GROUND, 0] <= 0
    r = kin.rollout(s, np.asarray([[0] + [J] * 7], np.int64), params, arena)
    assert r.mode[0, 1] != kin.M_GLIDE and r.mode[0, 2] == kin.M_GLIDE
    assert fp._glide_press(r.mode, 0, 1, int(s[kin.MODE, 0])) == "opens"
    # the prefix lands her (the umbrella ends on the floor): a press after it is a jump
    s = _state(params, arena, low)
    assert s[kin.MODE, 0] == kin.M_GLIDE
    r = kin.rollout(s, np.asarray([[0, 0, 0] + [J] * 8], np.int64), params, arena)
    assert r.mode[0, 3] != kin.M_GLIDE and r.vel[0, 4:10, 1].max() > 10                   # off the floor again
    assert fp._glide_press(r.mode, 0, 3, kin.M_GLIDE) is None
    # standing: a jump
    r = _roll(params, arena, [0] + [J] * 8)
    assert fp._glide_press(r.mode, 0, 1, 0) is None
    # no rollout row (BIND): the observed start
    assert fp._glide_press(r.mode, -2, 1, kin.M_GLIDE) == "in" and fp._glide_press(r.mode, -2, 1, 0) is None


# ---- the real planner's tick --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("on", [False, True])
def test_in_the_umbrella_the_old_hold_neither_binds_nor_is_renewed(params, arena, monkeypatch, on):
    """ep9 F51210's shape: floating, J held 47 frames and in flight, a hold left from a press that opened the umbrella."""
    monkeypatch.setattr(fp, "GLIDE_JUMP_HOLD", on)
    s = _state(params, arena, _glide_masks(params, arena)[0])
    pl = _real(params, arena)
    pl.jump_until = pl.ticks + 20
    _tick(pl, s, 100, [J], _j_held(47))
    keep = pl.last_sel["keep"]
    first = int(pl.last_sel["cmd"][pl.last_sel["first"], 0])
    if not on:
        assert not keep.all()                                            # off: the old hold ranks the J releases last
        assert pl.jump_until == (20 if first & J else -1) and "glide_hold" not in pl.last_info
        return
    assert keep.all()                                                    # on: no row ranked by the old hold
    assert pl.jump_until <= pl.ticks                                     # and none renewed for the float
    note = pl.last_info["glide_hold"]
    assert note["glide"] and note["cleared"] == 20
    assert (note.get("skip") == "in") == bool(first & J)


@pytest.mark.parametrize("on", [False, True])
def test_a_chosen_j_in_the_umbrella_commits_no_hold(params, arena, monkeypatch, on):
    monkeypatch.setattr(fp, "GLIDE_JUMP_HOLD", on)
    monkeypatch.setattr(fp, "veto", _first_key(True))
    s = _state(params, arena, _glide_masks(params, arena)[0])
    pl = _real(params, arena)
    res = _tick(pl, s, 100, [J], _j_held(47))
    assert res.mask & J
    if on:
        assert pl.jump_until == -1 and pl.last_info["glide_hold"]["skip"] == "in"
        assert pl.audit.glide_hold_skipped == 1
    else:
        assert pl.jump_until > pl.ticks                                   # off: a float committed as a jump


@pytest.mark.parametrize("on", [False, True])
def test_a_press_that_opens_the_umbrella_commits_no_hold(params, arena, monkeypatch, on):
    monkeypatch.setattr(fp, "GLIDE_JUMP_HOLD", on)
    monkeypatch.setattr(fp, "veto", _first_key(True))
    s = _state(params, arena, [J] * 12 + [0] * 4)
    pl = _real(params, arena)
    res = _tick(pl, s, 100, [0], kin.HoldState.idle(1))
    assert res.mask & J
    if on:
        assert pl.jump_until == -1 and pl.last_info["glide_hold"] == {"glide": False, "cleared": 0, "skip": "opens",
                                                                       "n": pl.last_info["glide_hold"]["n"]}
    else:
        assert pl.jump_until > pl.ticks


def test_after_the_prefix_left_the_umbrella_a_jump_commits_its_hold_and_no_jump_revives_nothing(params, arena,
                                                                                              monkeypatch):
    monkeypatch.setattr(fp, "GLIDE_JUMP_HOLD", True)
    s = _state(params, arena, _glide_masks(params, arena)[1])
    assert s[kin.MODE, 0] == kin.M_GLIDE
    # a jump pressed once the prefix has landed her
    monkeypatch.setattr(fp, "veto", _first_key(True))
    pl = _real(params, arena)
    pl.jump_until = pl.ticks + 20
    t0 = pl.ticks
    res = _tick(pl, s, 100, [0, 0, 0], _j_held(47))
    held = res.cmd & J
    n = int(np.argmin(held != 0)) if (held == 0).any() else len(held)
    r = kin.rollout(s, np.concatenate([[0, 0, 0], res.cmd])[None].astype(np.int64), params, arena)
    assert r.mode[0, 3] != kin.M_GLIDE and r.mode[0, 4] != kin.M_GLIDE                   # out before the press
    assert pl.jump_until == t0 + n and n > 0                                               # the old rule's hold
    note = pl.last_info["glide_hold"]
    assert note == {"glide": True, "cleared": 20, "armed": n} and pl.audit.glide_hold_armed_after == 1
    # the same tick without a jump: the old hold stays gone
    monkeypatch.setattr(fp, "veto", _first_key(False))
    pl = _real(params, arena)
    pl.jump_until = pl.ticks + 20
    res = _tick(pl, s, 100, [0, 0, 0], _j_held(47))
    assert not res.mask & J and pl.jump_until == -1 and pl.last_info["glide_hold"] == {"glide": True, "cleared": 20}


def test_a_jump_outside_the_umbrella_keeps_its_hold_and_keys_with_the_switch_on(params, arena, monkeypatch):
    """Rising from a real jump (J held 4 frames, its hold running): the same rows, ranks, choice and hold either way."""
    s = _state(params, arena, [J] * 4)
    assert s[kin.MODE, 0] != kin.M_GLIDE and s[kin.GROUND, 0] <= 0
    out = []
    for on in (False, True):
        monkeypatch.setattr(fp, "GLIDE_JUMP_HOLD", on)
        pl = _real(params, arena)
        pl.jump_until = pl.ticks + 10
        res = _tick(pl, s, 100, [J], _j_held(4))
        out.append((res.name, int(res.mask), pl.last_sel["keep"].copy(), pl.jump_until, pl.last_info.get("glide_hold")))
    (n0, m0, k0, j0, g0), (n1, m1, k1, j1, g1) = out
    assert (n0, m0, j0) == (n1, m1, j1) and (k0 == k1).all() and not k0.all()   # the hold binds the same way
    assert g0 is None and g1 is None
