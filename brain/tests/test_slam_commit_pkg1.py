"""Task 182 package 1 (SSBOT_FORUM_SLAM_COMMIT; the person 11-12 "继续包1和包2吧", docs/plans/forum_clapper_committed_chain.md
7.1, 5.2, 4.4): the slam playbook from its jump (or the Clawline's press) to the bounce hand-off or its own bounce's apex is one
committed link. The policy steps it on every tick of that span, the B2 chain gets no keys (gate "slam_play"), and a run that
loses the keys from its jump on ends there instead of waking at Slam 0 with a late press (b2 B04 12082, r2 bout 31 95655)."""
from types import SimpleNamespace as NS

import pytest

from ssbot.combat import slam_play as sp
from ssbot.train import forum_planner_policy as mod
from ssbot.train.forum_planner_policy import ForumPlannerPolicy as Policy
from tests.test_b2_policy_priority import Script, run_arbitration, selected
from tests.test_slam_play import slam_state, state


@pytest.fixture(autouse=True)
def commit_on(monkeypatch):
    # the switch follows SSBOT_FORUM_V2 (on in production); the tests' clean environment has no v2
    monkeypatch.setattr(sp, "COMMIT", True)


def trace(x0=5.0, f0=1000, bounce=True):
    """The toy slam of test_slam_play.simulate (antic 48, a mask for STATE f lands at f + 2, the bounce vy 17 from the press + 4
    for 15 frames, then falling), recording before each tick - the policy reads committed() before it steps the script - the
    run's phase, committed(STATE) and yield_ends_run()."""
    play = sp.SlamPlay(sp.PlayCfg())
    cx, face = 31.0, -1
    hx = cx + face * x0
    pending, press, air_from, rows = {}, None, None, {}
    for k in range(-5, 120):
        f = f0 + k
        m = pending.pop(f, None)
        if m is not None:
            if m & sp.M_J and air_from is None:
                air_from = k
            if m & sp.M_A and press is None:
                press = k
        ground = air_from is None or k > air_from + 60
        st, tin = slam_state(k)
        vy = 0.0
        if bounce and press is not None and k >= press + 4:
            vy = 17.0 if k < press + 19 else -5.0
        s = state(f, st, tin, cx=cx, hx=hx, ground=ground, vy=vy)
        r = play.run
        rows[k] = (None if r is None else r.phase, play.committed(s), play.yield_ends_run(s))
        out = play.step(f, s, ground)
        if out is not None:
            pending[f + 2] = out
    return play, rows, press


def test_committed_from_the_jump_to_the_apex():
    play, rows, press = trace()
    c = play.cfg
    jump_tick = c.k_jump - sp.SEND_AHEAD                  # the tick whose mask is the jump: committed from the next tick
    assert press == c.k_press
    assert not any(rows[k][1] or rows[k][2] for k in range(-5, jump_tick + 1))
    assert rows[jump_tick + 1] == ("jump", True, True)
    rise_end = press + 19                                 # the bounce rises through press + 18
    assert all(rows[k][1] for k in range(jump_tick + 1, rise_end))
    after_apex = [k for k in range(rise_end, 120) if rows[k][0] == "after"]
    assert after_apex and not any(rows[k][1] for k in after_apex)           # past the apex: not committed ...
    assert all(rows[k][2] for k in after_apex)                              # ... but a yield still ends the run
    assert play.done[-1].phase == "done"


def test_a_press_without_a_bounce_stays_committed_until_the_scripts_own_abort():
    play, rows, press = trace(bounce=False)
    c = play.cfg
    jump_tick = c.k_jump - sp.SEND_AHEAD
    assert play.done[-1].why == "no bounce"
    live = [k for k in rows if rows[k][0] in sp.COMMIT_PHASES]
    assert live and min(live) == jump_tick + 1 and all(rows[k][1] for k in live)


@pytest.mark.parametrize("phase", ["wait", "land", "walk", "cs_pre", "done", "abort"])
def test_before_the_jump_nothing_is_committed(phase):
    play = sp.SlamPlay(sp.PlayCfg())
    play.run = sp.Run(iid=7, fa=1000, face=-1, phase=phase)
    s = state(1030, "Slam Antic", 0.5, vy=0.0)
    assert not play.committed(s) and not play.yield_ends_run(s)


@pytest.mark.parametrize("phase", ["jump", "air", "cs_lock", "cs_strike"])
def test_jump_and_clawline_lock_phases_are_committed(phase):
    play = sp.SlamPlay(sp.PlayCfg())
    play.run = sp.Run(iid=7, fa=1000, face=-1, phase=phase)
    s = state(1030, "Slam Antic", 0.5, vy=-3.0)
    assert play.committed(s) and play.yield_ends_run(s)


def test_after_phase_commitment_reads_her_rise():
    play = sp.SlamPlay(sp.PlayCfg())
    play.run = sp.Run(iid=7, fa=1000, face=-1, phase="after")
    assert play.committed(state(1050, "Slam 0", 0.0, vy=0.0))             # pressed, no bounce yet
    play.run.bounced = True
    assert play.committed(state(1055, "Slam 1", 0.0, vy=12.0))            # rising
    assert not play.committed(state(1070, "Slam Recover", 0.0, vy=0.0))   # the apex
    assert not play.committed(None) and play.yield_ends_run(None)


@pytest.mark.parametrize("kwargs,reason", [
    ({"slam_commit": True}, "slam_play"),
    ({"slam_commit": True, "asw_crit": True}, "asw_crit"),
    ({"slam_commit": True, "low_crit": True}, "low_crit"),
    ({"slam_commit": True, "m2_on": True}, "m2"),
    ({"slam_commit": True, "supervisor": True}, "supervisor")])
def test_policy_gate_slam_play_is_last(kwargs, reason):
    flags = dict(low_crit=False, asw_crit=False, m2_on=False, supervisor=False)
    flags.update(kwargs)
    assert Policy._b2_policy_gate(**flags) == reason


class Slam(Script):
    """The playbook stand-in: yield_ends_run() answers ends."""
    def __init__(self, mask=16, ends=False):
        super().__init__(mask=mask)
        self.ends = ends

    def yield_ends_run(self, s):
        return self.ends


@pytest.mark.parametrize("stage", ["approach", "commitment", "manual_commitment"])
def test_a_committed_run_keeps_the_keys_over_a_selected_chain(stage):
    p, res = selected(stage, 2)
    out = run_arbitration(p, res, slam_commit=True, slam=Slam(ends=True))
    assert (out["own"], out["mask"], out["play"]) == ("slam", 16, 16)
    assert p.slam_play.stepped == [2599] and not p.slam_play.aborted
    assert p.chain_native.policy_gate_reason == "slam_play" and p.counts["slam_commit_gate"] == 1
    assert p.rune_lowhop.yielded == [2599] and p.evade_chase.yielded == [2599]


def test_without_the_commitment_the_chain_keeps_its_slot():
    p, res = selected("approach", 2)
    out = run_arbitration(p, res, slam=Slam(ends=False))
    assert out["own"] == "chain" and not p.slam_play.stepped and not p.slam_play.aborted


@pytest.mark.parametrize("flags,why", [({"low_crit": True}, "low_crit"), ({"asw_crit": True}, "asw_crit"),
                                      ({"m2": NS(took=False)}, "m2")])
def test_a_committed_run_a_critical_owner_takes_ends(flags, why):
    p, res = selected("approach", 2)
    run_arbitration(p, res, slam_commit=True, slam=Slam(ends=True), **flags)
    assert not p.slam_play.stepped and p.slam_play.aborted == ["yielded to " + why]
    assert p.counts["slam_commit_yield"] == 1


def test_a_run_past_its_apex_ends_when_the_chain_takes_the_keys():
    p, res = selected("approach", 2)
    out = run_arbitration(p, res, slam=Slam(ends=True))
    assert out["own"] == "chain" and not p.slam_play.stepped and p.slam_play.aborted == ["yielded to chain"]


def test_switch_off_is_the_old_arbitration(monkeypatch):
    monkeypatch.setattr(mod.slam_play, "COMMIT", False)
    p, res = selected("approach", 2)
    out = run_arbitration(p, res, slam=Slam(ends=True))
    assert out["own"] == "chain" and not p.slam_play.stepped and not p.slam_play.aborted


class Chain:
    """A B2 chain stand-in for the goal step: no real bounce; goal_preferences answers a new prefs object."""
    arm = "B"
    _transfer_goal = None

    def __init__(self):
        self.calls = []

    def observe_bounce_goal(self, state, prefs, run, game_time=None):
        return False

    def own_bounce_now(self, state):
        return False

    def goal_preferences(self, state, prefs, *, handoff):
        self.calls.append(handoff)
        return NS(**vars(prefs))


def goal_policy(committed):
    p = Policy.__new__(Policy)
    p.chain_native = Chain()
    aborted = []
    p.slam_play = NS(run=NS(phase="jump", bounced=False), committed=lambda s: committed, abort=aborted.append)
    p.tac = None
    return p, aborted


def test_no_chain_goal_is_bound_over_a_committed_run():
    p, aborted = goal_policy(True)
    prefs = NS(target=8)
    assert p._chain_goal_preferences({"f": 1030}, prefs) is prefs
    assert p.chain_native.calls == [] and not aborted


def test_an_uncommitted_run_keeps_todays_goal_step(monkeypatch):
    p, aborted = goal_policy(False)
    prefs = NS(target=8)
    out = p._chain_goal_preferences({"f": 1030}, prefs)
    assert out is not prefs and p.chain_native.calls == [False] and aborted == ["observed target transfer: goal handoff"]
    monkeypatch.setattr(mod.slam_play, "COMMIT", False)
    p, aborted = goal_policy(True)
    assert p._chain_goal_preferences({"f": 1030}, prefs) is not prefs and aborted
