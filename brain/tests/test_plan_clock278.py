"""Task 182 seq 278: the ordinary hand-back clock in frames (forum_planner._plan_frame / _plan_age / _age_commitments /
_note_plan_frame). A decision tick the live loop skipped (no STATE processed for that frame) still lets a frame pass:
the carried plan (CONTINUE) moves on by the frames it has run, the committed jump hold (jump_until) and macro
(macro_until) lose the skipped frames once, ForumPlanner.ticks stays a tick count, hold_row stays as it was."""
import random
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import candidates as cmod
from ssbot.combat import forum_planner as fp
from ssbot.combat.forum_planner import ForumConfig, ForumPlanner
from ssbot.combat.planner import PlannerConfig
from ssbot.knowledge import kinematics as kin
from tests.test_forum_planner import FLOOR, _ctx, _prefs, _reed_forecaster, _world, arena, params  # noqa: F401


def _ws(frame):
    return NS(stamp=NS(frame=frame))


# ---- the frames -------------------------------------------------------------------------------------------------------

def test_the_plan_frame_is_the_first_planned_masks_frame():
    assert fp._plan_frame(_ws(100), np.zeros(1, np.int64)) == 102
    # an older observation with a longer in-flight prefix plans the same frame (fo + P + 1 = f + 2)
    assert fp._plan_frame(_ws(99), np.zeros(2, np.int64)) == 102
    assert fp._plan_frame(None, np.zeros(1, np.int64)) == 2


def test_the_plan_age_is_the_frames_since_the_plans_own_frame():
    p = NS(prev_d=102)
    pre = np.zeros(1, np.int64)
    assert fp._plan_age(p, _ws(101), pre) == 1          # consecutive: the old one-frame step
    assert fp._plan_age(p, _ws(102), pre) == 2          # one skipped frame
    assert fp._plan_age(p, _ws(105), pre) == 5          # several
    assert fp._plan_age(p, _ws(100), pre) == 1          # repeated frame: the old step, nothing counted
    assert fp._plan_age(p, _ws(97), pre) == 1           # backward
    assert fp._plan_age(NS(prev_d=None), _ws(130), pre) == 1
    assert fp._plan_age(NS(), _ws(130), pre) == 1


# ---- the committed jump hold and macro --------------------------------------------------------------------------------

def test_skipped_frames_come_off_the_committed_jump_and_macro_once():
    p = NS(ticks=50, jump_until=60, macro_until=55, _clock_d=None)
    fp._age_commitments(p, 102)
    assert (p.jump_until, p.macro_until, p._clock_d) == (60, 55, 102)         # first tick: reference only
    fp._age_commitments(p, 103)
    assert (p.jump_until, p.macro_until, p._clock_d) == (60, 55, 103)         # consecutive: unchanged
    fp._age_commitments(p, 105)
    assert (p.jump_until, p.macro_until, p._clock_d) == (59, 54, 105)         # one frame (104) had no tick
    fp._age_commitments(p, 105)
    assert (p.jump_until, p.macro_until, p._clock_d) == (59, 54, 105)         # repeated frame
    fp._age_commitments(p, 104)
    assert (p.jump_until, p.macro_until, p._clock_d) == (59, 54, 105)         # backward: the reference stays
    fp._age_commitments(p, 106)
    assert (p.jump_until, p.macro_until) == (59, 54)                          # 104 / 105 not counted again
    fp._age_commitments(p, 110)
    assert (p.jump_until, p.macro_until) == (56, 51)                          # three frames had no tick


def test_expired_and_released_commitments_are_not_touched_and_a_long_skip_expires_them():
    p = NS(ticks=50, jump_until=50, macro_until=-1, _clock_d=100)
    fp._age_commitments(p, 104)
    assert (p.jump_until, p.macro_until) == (50, -1)
    p = NS(ticks=50, jump_until=52, macro_until=51, _clock_d=100)
    fp._age_commitments(p, 106)                                               # five frames without a tick
    assert p.jump_until - p.ticks == -3 and p.macro_until - p.ticks == -4
    assert p.jump_until <= p.ticks and not p.macro_until > p.ticks           # a new press may commit; no macro kept


def test_the_aged_remainders_equal_a_frame_clock():
    """The #348 candidate advanced ticks itself by the frames elapsed. Here ticks stays a tick count and the two
    timers are aged instead: at every tick their remaining amounts and their active / expired state equal the
    candidate's, over random skips, presses, releases, macros and re-commits."""
    rng = random.Random(278)
    for _ in range(200):
        p = NS(ticks=0, jump_until=-1, macro_until=-1, _clock_d=None)
        c = dict(ticks=0, jump_until=-1, macro_until=-1, last=None)
        d = 1000
        for _ in range(60):
            d += 1 if rng.random() < 0.7 else rng.randint(2, 5)
            fp._age_commitments(p, d)
            if c["last"] is not None and d - c["last"] > 1:
                c["ticks"] += d - c["last"] - 1
            c["last"] = d
            for k in ("jump_until", "macro_until"):
                a_on, c_on = getattr(p, k) > p.ticks, c[k] > c["ticks"]
                assert a_on == c_on
                if a_on:
                    assert getattr(p, k) - p.ticks == c[k] - c["ticks"]
            # this tick's selection (the planner's own rules: a jump commits only when the last one is over)
            r = rng.random()
            if r < 0.3:
                n = rng.randint(1, 30)
                if p.jump_until <= p.ticks:
                    p.jump_until = p.ticks + n
                if c["jump_until"] <= c["ticks"]:
                    c["jump_until"] = c["ticks"] + n
            elif r < 0.45:
                p.jump_until = c["jump_until"] = -1
            if rng.random() < 0.15:
                n = rng.randint(0, 25)
                p.macro_until, c["macro_until"] = p.ticks + n, c["ticks"] + n
            elif rng.random() < 0.1:
                p.macro_until = c["macro_until"] = -1
            p.ticks += 1
            c["ticks"] += 1


# ---- prev_d follows prev_cmd ------------------------------------------------------------------------------------------

def test_prev_d_follows_the_plan_the_tick_left():
    a, b = np.ones(3, np.int64), np.ones(3, np.int64)
    p = NS(prev_cmd=b, prev_d=90)
    fp._note_plan_frame(p, a, 104)
    assert p.prev_d == 104                         # a plan this tick left starts at this tick's frame
    fp._note_plan_frame(p, b, 105)
    assert p.prev_d == 104                         # the same plan carried over keeps its own frame
    p.prev_cmd = None
    fp._note_plan_frame(p, b, 106)
    assert p.prev_d is None                        # cleared (a native chain row, a B2 recovery or commitment)


def _b2_case(stage, *, bound=float("inf"), ordinary_wins=False):
    """ForumPlanner.tick's B2 arm on a stub chain whose install leaves prev_cmd as knife_chain_b2.install does
    (None, or the continuation's own command for a continuation)."""
    seen = []
    offer = NS(stage=stage, value=10.0, mask=1)
    ordinary = NS(J=30.0 if ordinary_wins else -5.0, S=0, forced_risk=False, t_ms={}, name="normal")
    chosen = NS(t_ms={}, mask=1)
    cont = np.full(8, 7, np.int64)

    def ordinary_tick(*a, **k):
        p.prev_cmd = np.full(8, 3, np.int64)          # the ordinary rows' own plan (overridden or kept)
        p.ticks += 1
        return ordinary

    def install(offer_, parent, *args):
        seen.append(offer_.stage)
        parent.prev_cmd = cont.copy() if offer_.stage == "continuation" else None
        return chosen

    chain = NS(b2=True, arm="B", propose=lambda *a: offer, first_allowed=lambda *a: True, install=install,
               continuation_value_bound=lambda prefs: bound, _note=lambda *a, **k: None)
    p = NS(chain_native=chain, ticks=10, jump_until=-1, macro_until=-1, prev_cmd=np.zeros(8, np.int64), prev_d=101,
           _clock_d=101, _ordinary_tick=ordinary_tick, measurement_enabled=False)
    return p, ordinary, chosen, seen


@pytest.mark.parametrize("stage,frame_kept", [("continuation", True), ("recovery", False), ("active", False),
                                               ("manual_commitment", False)])
def test_a_b2_install_leaves_its_own_plan_frame(stage, frame_kept):
    p, _, chosen, seen = _b2_case(stage)
    got = ForumPlanner.tick(p, _ws(100), np.zeros(kin.K), None, np.zeros(1, np.int64), None, None, None)
    assert got is chosen and seen == [stage]
    assert p.prev_d == (102 if frame_kept else None)


def test_an_ordinary_result_overridden_by_b2_leaves_b2s_plan_frame():
    # value bound finite and not dominated: the ordinary rows run first, then B2 installs over them
    p, _, chosen, seen = _b2_case("recovery", bound=20.0)
    assert ForumPlanner.tick(p, _ws(100), np.zeros(kin.K), None, np.zeros(1, np.int64), None, None, None) is chosen
    assert p.prev_cmd is None and p.prev_d is None
    p, _, chosen, _ = _b2_case("continuation", bound=20.0)
    ForumPlanner.tick(p, _ws(100), np.zeros(kin.K), None, np.zeros(1, np.int64), None, None, None)
    assert (p.prev_cmd == 7).all() and p.prev_d == 102


def test_an_ordinary_result_that_beats_the_offer_keeps_its_own_plan_frame():
    p, ordinary, _, seen = _b2_case("continuation", ordinary_wins=True)
    assert ForumPlanner.tick(p, _ws(100), np.zeros(kin.K), None, np.zeros(1, np.int64), None, None, None) is ordinary
    assert seen == [] and (p.prev_cmd == 3).all() and p.prev_d == 102


def test_b2_ticks_keep_the_clock_so_a_skip_is_counted_once():
    p, _, _, _ = _b2_case("active")
    p.jump_until, p.macro_until = 30, 25
    for frame in (100, 101):                      # B2 owns two consecutive ticks
        ForumPlanner.tick(p, _ws(frame), np.zeros(kin.K), None, np.zeros(1, np.int64), None, None, None)
    assert (p.jump_until, p.macro_until) == (30, 25) and p._clock_d == 103
    ForumPlanner.tick(p, _ws(103), np.zeros(kin.K), None, np.zeros(1, np.int64), None, None, None)   # 102 skipped
    assert (p.jump_until, p.macro_until) == (29, 24)


def test_the_disabled_arm_keeps_the_same_object_and_args():
    sentinel = object()
    calls = []
    p = NS(chain_native=None, _ordinary_tick=lambda *a: (calls.append(a), sentinel)[1])
    args = (_ws(100), None, None, np.zeros(1, np.int64), None, None, None)
    assert ForumPlanner.tick(p, *args) is sentinel and calls == [args]


# ---- the real planner: CONTINUE, reset, hold_row ----------------------------------------------------------------------

def _real(params, arena):
    return ForumPlanner(params, arena, PlannerConfig(T=36, threads=2, variants="bounds_lo"), ForumConfig(deadline_ms=50.0))


def test_the_real_continue_row_moves_on_by_the_frames_run(params, arena, monkeypatch):
    shifts = []
    real = cmod.continue_plan

    def rec(prev, shift, T):
        shifts.append(shift)
        return real(prev, shift, T)

    monkeypatch.setattr(cmod, "continue_plan", rec)
    pl = _real(params, arena)
    f = _reed_forecaster(None).forecast(0.8)
    x = 24.0
    start = kin.initial_state(params, x, FLOOR + params.foot)
    for frame in (100, 101, 103, 107, 108):
        ws = _world(x)
        ws.stamp.frame = frame
        pl.tick(ws, start, kin.HoldState.idle(1), np.zeros(1, np.int64), f, _prefs(None, x), _ctx(kill_hp=5.0))
        assert pl.prev_cmd is not None and pl.prev_d == frame + 2
    assert shifts == [1, 2, 4, 1]                 # no CONTINUE on the first tick; 102, 104-106 had no tick
    assert pl.ticks == 5                          # ticks stays a tick count
    pl.hold_row = np.zeros(4, np.int64)           # M4d2 / stage N hold: the bridge is already aligned by frames
    ws = _world(x)
    ws.stamp.frame = 111
    pl.tick(ws, start, kin.HoldState.idle(1), np.zeros(1, np.int64), f, _prefs(None, x), _ctx(kill_hp=5.0))
    assert shifts == [1, 2, 4, 1]
    pl.reset()
    assert pl.prev_d is None and pl._clock_d is None and pl.prev_cmd is None
    assert pl.jump_until == pl.macro_until == -1 and pl.ticks == 0
