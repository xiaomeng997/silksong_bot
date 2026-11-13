"""Task 179 seq 259: the chase's distance brake must not take the planner's move away from her while she falls on the body
(live w13_task182_20261107T070029Z 2583-2588), and every other brake, chase key and gate stays. Numbers are the recording's."""
from collections import Counter
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import evade_chase as ec
from ssbot.combat import slam_play as sp
from ssbot.knowledge import kinematics as K
from ssbot.train import forum_planner_policy as mod
from ssbot.train.forum_planner_policy import ForumPlannerPolicy as Policy
from tests.test_b2_policy_priority import Script, arbitration_code
from tests.test_sp8c import ev_state

IID = 335476
M_J = 1
DASH_R = sp.M_R | sp.M_DASH


def live(f, k, cx, foot, vy, x=24.179, half=0.25, top=2.079):
    """Evade Scuttle at frame k, the Clapper facing right and sliding left at 15 u/s, her box at x in the air."""
    s = ev_state(f, k, x - cx, cx=cx, flip=True, ground=False, clip="Recoil Twirl")
    s["ents"][0].update(iid=IID, vel=[-15.0, 0.0])
    s["hero"].update(box=[x - half, foot, x + half, foot + top], vel=[0.0, vy], facing=-1)
    return s


# the five live ticks: (f, k, its x, her foot, her vy)
LIVE = [(2583, 0, 22.71, 6.953, -19.8), (2584, 1, 22.41, 6.533, -21.0), (2585, 2, 22.11, 6.089, -22.2)]


def stepped(s, ground=False, accepting=True, ch=None):
    ch = ch or ec.EvadeChase(one=True, two=False)
    m = ch.step(s["f"], s, ground, accepting)
    return ch, m


def test_the_live_ticks_over_the_body_yield_to_the_move_away():
    # 2583: d = 1.969 over the body (reach 2.5); 2584: 2.269
    for f, k, cx, foot, vy in LIVE[:2]:
        ch, m = stepped(live(f, k, cx, foot, vy))
        assert m == 0 and ch.active()
        assert ch.yields_brake_to(DASH_R)
        assert ch.yields_brake_to(sp.M_R)                 # the MOVE(R) row of 2586 is a move away too
    # 2585: d = 2.569, her box past its front on the mask's frame: the plain brake again
    f, k, cx, foot, vy = LIVE[2]
    ch, m = stepped(live(f, k, cx, foot, vy))
    assert m == 0 and not ch.yields_brake_to(DASH_R)


@pytest.mark.parametrize("mask", [0, M_J, sp.M_A, sp.M_L, sp.M_L | sp.M_DASH, sp.M_L | sp.M_R, sp.M_DASH])
def test_a_mask_that_is_no_move_away_keeps_the_brake(mask):
    f, k, cx, foot, vy = LIVE[0]
    ch, m = stepped(live(f, k, cx, foot, vy))
    assert m == 0 and not ch.yields_brake_to(mask)


def test_she_is_rising_or_high_above_or_on_the_ground_or_without_input_the_brake_stays():
    # recorded 0bf1b27f 3080: over the body, rising from a bounce, the planner moving away: that chase went on to its slash
    ch, m = stepped(live(3080, 0, 22.71, 8.219, 6.6, x=24.016))
    assert m == 0 and not ch.yields_brake_to(DASH_R)
    # rising with her foot still under its top: no fall to get away from
    ch, m = stepped(live(3080, 0, 22.71, 6.0, 1.0, x=24.016))
    assert m == 0 and not ch.yields_brake_to(DASH_R)
    # far above the top: its slide clears her first
    ch, m = stepped(live(2583, 0, 22.71, 12.0, -5.0))
    assert m == 0 and not ch.yields_brake_to(DASH_R)
    f, k, cx, foot, vy = LIVE[0]
    ch, m = stepped(live(f, k, cx, foot, vy), ground=True)
    assert m == 0 and not ch.yields_brake_to(DASH_R)
    ch, m = stepped(live(f, k, cx, foot, vy), accepting=False)
    assert m == 0 and not ch.yields_brake_to(DASH_R)


def test_past_its_centre_the_run_has_no_away_key_and_the_brake_stays():
    # Sol seq 260: a run started in front of it (2583), the next tick she is 1 u past its centre: the run's away key (from its
    # starting side) points at the body. d on the mask's frame = -0.5; no key is given way to, in either direction.
    f, k, cx, foot, vy = LIVE[0]
    ch, m = stepped(live(f, k, cx, foot, vy))
    assert m == 0 and ch.active() and ch.yields_brake_to(DASH_R)
    f, k, cx, foot, vy = LIVE[1]
    s = live(f, k, cx, foot, vy, x=cx - 1.0)
    m = ch.step(f, s, False, True)
    assert m == 0 and ch.active() and ch.run.face == 1
    assert (s["hero"]["box"][0] + s["hero"]["box"][2]) / 2.0 - (cx - 0.5) == pytest.approx(-0.5)
    assert not ch.yields_brake_to(sp.M_R) and not ch.yields_brake_to(DASH_R) and not ch.yields_brake_to(sp.M_L)
    # at the centre itself on the mask's frame too (d = 0): the proven side only
    f0, k0, cx0, foot0, vy0 = LIVE[0]
    ch, m = stepped(live(f0, k0, cx0, foot0, vy0))
    m = ch.step(f, live(f, k, cx, foot, vy, x=cx - 0.5), False, True)
    assert m == 0 and ch.active() and not ch.yields_brake_to(DASH_R)


def test_in_front_of_the_body_the_brake_stays():
    # recorded observe_bait 4104: d = 3.599, 1.1 u off its front, landing: a real brake
    s = live(4104, 0, 22.71, 3.495, -12.0, x=22.71 + 3.099)
    ch, m = stepped(s)
    assert m == 0 and not ch.yields_brake_to(DASH_R)


def test_the_key_must_latch():
    f, k, cx, foot, vy = LIVE[0]
    ch, m = stepped(live(f, k, cx, foot, vy))
    assert not ch.yields_brake_to(DASH_R, lambda m_: m_ & ~sp.M_R)
    assert ch.yields_brake_to(DASH_R, lambda m_: m_)


def test_the_answer_is_for_this_tick_only():
    f, k, cx, foot, vy = LIVE[0]
    ch, m = stepped(live(f, k, cx, foot, vy))
    assert ch.yields_brake_to(DASH_R)
    # the next tick she is far enough: the chase's own key toward it, nothing to yield
    s = live(f + 1, k + 1, cx - .25, foot, vy, x=30.0)
    m = ch.step(s["f"], s, False, True)
    assert m & sp.M_L and not ch.yields_brake_to(DASH_R)


def test_the_room_stop_is_no_distance_brake():
    # the other one's span ahead (SSBOT_FORUM_TWO_GUARD): the 0 that keeps her out of it stays, whatever the mask
    s = live(2583, 0, 22.71, 6.953, -19.8, x=30.0)
    ch = ec.EvadeChase(one=True, two=False)
    ch.run = ec.Chase(iid=IID, face=1, f0=2583, k0=2, x0=7.0, ground0=False, hp0=9)
    m = ch._step_run(ch.run, 2583, 2, s, s["ents"][0], False, True, None, room=0.05)
    assert m == 0 and ch.run.guard_stops == 1 and not ch.yields_brake_to(DASH_R)


# ---- the production arbitration statements of ForumPlannerPolicy.act (tests.test_b2_policy_priority.arbitration_code)


def arbitrate(s, planner_mask, *, ch=None, sup=None, slam=None, prefix=(0,), ground=False, f=None):
    p = Policy.__new__(Policy)
    p.chain_native = NS(b2=False, arm=None, candidate_generation=False, final=lambda *a: None)
    p.tac = None
    p.sc = NS(pq=None)
    p.pause_owned = False
    p.m2 = None
    p.wpress = None
    p.air_show = None
    p._play_tick = None
    p.v2feed = None
    p.counts = Counter()
    p._cogfly = lambda *a: None
    p.cog = {"frames": set()}
    p.slam_play = Script(mask=slam)
    p.claw = Script(mask=None)
    p.cast_stab = Script(mask=None)
    p.rune_lowhop = Script(mask=None)
    p.evade_chase = ch or ec.EvadeChase(one=True, two=False)
    p.two = None
    p._wake_f = None
    p.enc = NS(name="w13")
    f = s["f"] if f is None else f
    res = NS(name="DASH(R)+jump48L", mask=planner_mask)
    scope = dict(self=p, res=res, r=NS(mask=sup), s=s, raw=s, f=f, fo=f,
                 ws=NS(stamp=NS(t_game_s=1.), hero=NS(contact=NS(v="GROUND" if ground else "AIR"))), S0=None,
                 prefix=np.asarray(prefix, np.int64), hold=K.HoldState.idle(1), prefs=NS(target=IID), esc_on=False, wt=None, fcast=None,
                 m2_mask=None, b2_priority=None, b2_critical=None, air_tick=False,
                 slam_commit=False)            # Task 182 package 1: act's flag from SlamPlay.committed (no committed run here)
    # One namespace (module globals + act's locals): act's generator expressions (seq 312's middle_jump reads prefs for every
    # Clapper) see act's locals as they do in act; exec with a separate locals dict raised NameError since e1ac76e5
    ns = dict(mod.__dict__)
    ns.update(scope)
    exec(arbitration_code(), ns)
    return p, ns


def test_production_the_move_away_goes_out_and_the_chase_ends():
    f, k, cx, foot, vy = LIVE[0]
    p, out = arbitrate(live(f, k, cx, foot, vy), DASH_R)
    assert (out["own"], out["mask"], out["play"]) == ("plan", DASH_R, None)
    assert p.counts["evade_air_escape"] == 1 and not p.counts["evade_chase"]
    assert not p.evade_chase.active()
    assert p.evade_chase.done[-1].phase == "abort" and p.evade_chase.done[-1].why == "air escape"
    assert p.evade_chase.stats()["end_abort_air escape"] == 1
    # the same slide is not chased again
    f, k, cx, foot, vy = LIVE[1]
    assert p.evade_chase.step(f, live(f, k, cx, foot, vy), False, True) is None


def test_production_a_toward_mask_stays_braked_and_the_chase_goes_on():
    f, k, cx, foot, vy = LIVE[0]
    p, out = arbitrate(live(f, k, cx, foot, vy), sp.M_L | sp.M_DASH)
    assert (out["own"], out["mask"], out["play"]) == ("chase", 0, 0)
    assert p.evade_chase.active() and p.counts["evade_chase"] == 1 and not p.counts["evade_air_escape"]


def test_production_a_normal_chase_key_still_overrides_the_planner():
    p, out = arbitrate(live(2600, 5, 22.71, 6.953, -19.8, x=29.0), DASH_R)
    assert out["own"] == "chase" and out["mask"] & sp.M_L and p.evade_chase.active()


def test_production_the_key_held_in_flight_keeps_the_brake():
    # L sent for f + 1: the hold filter keeps it through f + 2 and R waits: the move away would not latch on the mask's frame
    f, k, cx, foot, vy = LIVE[0]
    lat, _ = K.hold_filter(np.asarray([sp.M_L, DASH_R], np.int64), K.HoldState.idle(1))
    assert not int(lat[-1]) & sp.M_R
    p, out = arbitrate(live(f, k, cx, foot, vy), DASH_R, prefix=(sp.M_L,))
    assert (out["own"], out["mask"]) == ("chase", 0) and p.evade_chase.active()


def test_production_the_supervisor_and_committed_scripts_stay_above_it():
    f, k, cx, foot, vy = LIVE[0]
    p, out = arbitrate(live(f, k, cx, foot, vy), DASH_R, sup=sp.M_R)        # (the supervisor's own mask moving away too)
    assert out["mask"] == sp.M_R and p.evade_chase.done[-1].why == "supervisor" and not p.counts["evade_air_escape"]
    p, out = arbitrate(live(f, k, cx, foot, vy), DASH_R, slam=16)
    assert (out["own"], out["mask"]) == ("slam", 16) and not p.counts["evade_air_escape"]


def test_production_a_rune_over_the_way_ends_the_chase_as_before():
    # the hard gates close the run before any brake: the planner decides, with no escape count
    f, k, cx, foot, vy = LIVE[0]
    ch = ec.EvadeChase(one=True, two=False)
    ch._rune_in_way = lambda *a: True
    p, out = arbitrate(live(f, k, cx, foot, vy), DASH_R, ch=ch)
    assert (out["own"], out["mask"]) == ("plan", DASH_R) and not p.counts["evade_air_escape"]
    assert ch.why_not.get("rune") == 1 and not ch.active()
