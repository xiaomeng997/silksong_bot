"""Task 182 item 3, the second package (Sol seq 372 on #433; SSBOT_FORUM_MIDDLE_HANDOFF, default off; design 7.1 step 3
"第二包"): the chain's bounce follow-up that really lands between the two bodies after a real bounce off a slam is a one-shot
event; the policy reads it on that tick and sets the slam playbook's TWO_HANDOFF anchor (A, this tick's clock), so a slam the
other Clapper began meanwhile is TWO_HANDOFF's late start on the landing tick. Every start gate and limit is the playbook's own.
Off: nothing recorded, no anchor."""
from dataclasses import asdict

import pytest

from ssbot.combat import slam_play as sp
from ssbot.combat.knife_chain_commitment import MoveInstance
from ssbot.combat.knife_chain_transfer import ReturnGoal, TransferGoal
from tests.test_bounce_follow183 import BOUNCE_F, Bout, _landing_bout
from tests.test_sp10b import two, two_on  # noqa: F401  (two_on: the fixture, used by name)

SLAM = MoveInstance(8, BOUNCE_F - 52, "CC_SLAM")   # Bout's bounce source: the bounced Clapper's (iid 8) own slam
F_TEST = 3100


@pytest.fixture
def mh_on(monkeypatch):
    monkeypatch.setattr(sp, "MIDDLE_HANDOFF", True)


def _middle(monkeypatch):
    bout = Bout(monkeypatch)
    bout.run()
    landed = bout.notes("transfer_follow_landed")
    assert len(landed) == 1 and landed[0]["link"] == "middle"
    return bout, landed[0]["frame"]


# ---- the chain's event: only the middle's real normal completion after a real bounce off the bounced one's own slam


def test_off_records_nothing(monkeypatch):
    monkeypatch.setattr(sp, "MIDDLE_HANDOFF", False)
    bout, f = _middle(monkeypatch)
    assert bout.n.middle_completion is None
    assert not any(bout.notes(e) for e in ("middle_handoff_ready", "middle_handoff_none", "middle_handoff_expired"))
    assert bout.n.take_middle_completion(f) is None


def test_real_middle_completion_is_one_event_read_once_on_its_tick(monkeypatch, mh_on):
    bout, f = _middle(monkeypatch)
    ev = bout.n.middle_completion
    assert ev == dict(episode=bout.n.episode, frame=f, caster=8, bounce_f=BOUNCE_F, source=asdict(SLAM))
    ready = bout.notes("middle_handoff_ready")
    assert len(ready) == 1 and ready[0]["frame"] == f and ready[0]["caster"] == 8
    assert bout.n.take_middle_completion(f) == ev
    assert bout.n.take_middle_completion(f) is None and bout.n.middle_completion is None   # consumed once


def test_an_event_from_another_tick_or_episode_is_dropped_not_restamped(monkeypatch, mh_on):
    bout, f = _middle(monkeypatch)
    assert bout.n.take_middle_completion(f + 1) is None                  # a later tick: dropped, not this tick's
    exp = bout.notes("middle_handoff_expired")
    assert len(exp) == 1 and exp[0]["event_frame"] == f and bout.n.middle_completion is None
    bout, f = _middle(monkeypatch)
    bout.n.middle_completion["episode"] = bout.n.episode + 1             # another episode's leftover
    assert bout.n.take_middle_completion(f) is None and bout.notes("middle_handoff_expired")


def test_an_outer_landing_records_nothing(monkeypatch, mh_on):
    bout = _landing_bout(monkeypatch)
    bout.run()
    landed = bout.notes("transfer_follow_landed")
    assert len(landed) == 1 and landed[0]["link"] == "land"
    assert bout.n.middle_completion is None and not bout.notes("middle_handoff_ready")


def test_a_landing_outside_the_gap_records_nothing(monkeypatch, mh_on):
    bout = Bout(monkeypatch)
    real = type(bout.n)._follow_landing_inside          # a staticmethod (state, run)
    monkeypatch.setattr(type(bout.n), "_follow_landing_inside",
                        staticmethod(lambda state, run: (False,) + tuple(real(state, run)[1:])))
    bout.run()
    assert bout.notes("transfer_follow_missed") and not bout.notes("transfer_follow_landed")
    assert bout.n.middle_completion is None and not bout.notes("middle_handoff_ready")


@pytest.mark.parametrize("goal", [
    TransferGoal(8, 8, BOUNCE_F, 20., "BOUNCE", MoveInstance(7, BOUNCE_F - 52, "CC_SLAM")),     # the source is the other one's
    TransferGoal(8, 8, BOUNCE_F, 20., "BOUNCE", MoveInstance(8, BOUNCE_F - 52, "RUNE_TRANSFER")),  # not a slam
    TransferGoal(8, 8, BOUNCE_F, 20., "CAST", MoveInstance(8, BOUNCE_F - 52, "CC_SLAM")),       # not a bounce
    ReturnGoal(8, 8, BOUNCE_F, 20., "BOUNCE", MoveInstance(8, BOUNCE_F - 52, "CC_SLAM")),       # an L2 return (even labelled BOUNCE)
    None])
def test_no_observed_slam_bounce_source_names_no_a(monkeypatch, mh_on, goal):
    bout = Bout(monkeypatch)
    bout.n._transfer_goal = goal
    bout.n._note_middle_completion(F_TEST)
    assert bout.n.middle_completion is None
    none = bout.notes("middle_handoff_none")
    assert len(none) == 1 and none[0]["frame"] == F_TEST and not bout.notes("middle_handoff_ready")


def test_episode_reset_clears_a_pending_event(monkeypatch, mh_on):
    bout, f = _middle(monkeypatch)
    assert bout.n.middle_completion is not None
    bout.n.reset(bout.n.episode + 1)
    assert bout.n.middle_completion is None


# ---- the playbook's side: TWO_HANDOFF's own rule from the new anchor, every gate and limit unchanged


def _anchored(a_iid=7, t=10.0):
    p = sp.SlamPlay(sp.PlayCfg())
    assert p.run is None                         # the chain held the post-bounce: no run of the playbook's own
    return p, p.middle_handoff(a_iid, t)


def test_anchor_opens_bs_slam_as_a_late_start_on_the_landing_tick(two_on, monkeypatch):
    monkeypatch.setattr(sp, "TWO_HANDOFF", True)
    t = 10.0
    p, ok = _anchored(7, t)
    assert ok and p._ho == (7, t)
    # B (iid 8) in Slam Antic since 15 frames, she 5 u in front of it on the ground: B's run is the late start
    m = p.step(700, two(700, "Idle", 0.3, "Slam Antic", 15 / 60.0, hx=35.0), True, t_game=t)
    assert p.run is not None and p.run.iid == 8 and p.run.handoff and p.run.late
    assert p.run.phase == "walk" and m == 0
    assert p.stats()["handoff"] == 1


def test_anchor_late_start_limits_are_twohandoffs_own(two_on, monkeypatch):
    monkeypatch.setattr(sp, "TWO_HANDOFF", True)
    t = 10.0
    # antic frame 27 on the landing tick, inside the band: the jump at once (k 29), the press 18 frames later
    p, _ = _anchored(7, t)
    m = p.step(700, two(700, "Idle", 0.3, "Slam Antic", 27 / 60.0, hx=34.0), True, t_game=t)
    assert p.run.handoff and p.run.phase == "jump" and p.run.k_jump == 29 and m & sp.M_J and p.run.k_press_plan == 47
    # antic frame 31: past K_JUMP_LATE2 - no late start, the ordinary 'late'
    p, _ = _anchored(7, t)
    m = p.step(700, two(700, "Idle", 0.3, "Slam Antic", 31 / 60.0, hx=34.0), True, t_game=t)
    assert m is None and p.done[-1].iid == 8 and p.done[-1].why == "late" and not p.done[-1].handoff


def test_anchor_expires_after_ho_gap_f_on_its_own_clock(two_on, monkeypatch):
    monkeypatch.setattr(sp, "TWO_HANDOFF", True)
    t = 10.0
    p, _ = _anchored(7, t)
    later = t + (sp.HO_GAP_F + 1) / 60.0       # B's run opens 5 frames after the completion: no hand-off
    m = p.step(705, two(705, "Idle", 0.3, "Slam Antic", 15 / 60.0, hx=35.0), True, t_game=later)
    assert not (p.run is not None and p.run.handoff)
    assert not any(r.handoff for r in p.done)


def test_as_own_new_slam_is_no_late_start(two_on, monkeypatch):
    monkeypatch.setattr(sp, "TWO_HANDOFF", True)
    t = 10.0
    p, _ = _anchored(8, t)                    # the anchor names 8 itself (the bounced one slams again)
    p.step(700, two(700, "Idle", 0.3, "Slam Antic", 15 / 60.0, hx=35.0), True, t_game=t)
    assert not (p.run is not None and p.run.handoff)


def test_a_closed_slam_is_not_revived(two_on, monkeypatch):
    monkeypatch.setattr(sp, "TWO_HANDOFF", True)
    t = 10.0
    p, _ = _anchored(7, t)
    ta = t - 15 / 60.0                        # B's slam began 15 frames ago and its run was already closed
    p._closed_iid = 8
    p._closed_ta[8] = ta
    m = p.step(700, two(700, "Idle", 0.3, "Slam Antic", 15 / 60.0, hx=35.0), True, t_game=t)
    assert m is None and p.run is None


@pytest.mark.parametrize("ho,play", [(False, True), (True, False)])
def test_no_anchor_with_twohandoff_or_twoplay_off(monkeypatch, ho, play):
    monkeypatch.setattr(sp, "TWO_HANDOFF", ho)
    monkeypatch.setattr(sp, "TWO_PLAY", play)
    monkeypatch.setattr(sp, "LATE", True)
    p, ok = _anchored(7, 10.0)
    assert not ok and p._ho is None


def test_no_anchor_without_a(two_on, monkeypatch):
    monkeypatch.setattr(sp, "TWO_HANDOFF", True)
    p, ok = _anchored(None, 10.0)
    assert not ok and p._ho is None


def test_the_playbooks_own_landing_anchor_is_unchanged(two_on, monkeypatch):
    # TWO_HANDOFF's old path (A's own pressed run closing on her landing) still sets the anchor by itself
    monkeypatch.setattr(sp, "TWO_HANDOFF", True)
    from tests.test_sp10b import after_run
    p = sp.SlamPlay(sp.PlayCfg())
    p.run = after_run()
    t = 10.0 + 102 / 60.0
    p.step(700, two(700, "Idle", 0.3, "Slam Antic", 15 / 60.0, hx=35.0), True, t_game=t)
    assert p.done[0].iid == 7 and p.run is not None and p.run.iid == 8 and p.run.handoff and p.run.late
