"""Task 181 (Sol seq 251): the same-target bounce table / the real bounce under an L2 target change. The replay positives
are review181's (real L2, policy, planner, B2 geometry, before_send, sent); here the boundaries they found.
- the normal knife is B2's ordinary strike: from its press its own target's body is that strike's contact, not a blocked
  step (ob_on 3183: uncovered at the press, every baseline knife, with or without a target change);
- L2's target takes effect at the table's hand-back, the keys keep going until then; identities never mix;
- a real bounce hands off from a script run left over from before the chain took the keys (wtb3 2760)."""
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import knife_chain_air as AIR
from ssbot.combat import knife_chain_bounce_table as BT
from ssbot.combat import knife_chain_transfer as transfer
from ssbot.combat.knife_chain_commitment import MoveInstance, PathContact
from ssbot.combat.knife_chain_geometry import B2Geometry
from ssbot.knowledge import kinematics as K
from tests.test_bounce_table309 import FC, HIT, chain, prefs, scene

PRESS = HIT + 33


def anchored(monkeypatch):
    n = chain(monkeypatch)
    s = scene()
    BT.observe_frame(n, s)
    assert n.observe_bounce_goal(s, prefs(), NS(iid=7, fa=946, ta=2., phase="after"))
    n._clock = 20.
    return n, s


def tick(monkeypatch, n, f, contacts=(), l2=7, queued=0):
    """One B2 tick of the anchored table at frame f; its geometry answers the given contacts."""
    s = scene(f=f)
    s["ev"] = []
    BT.observe_frame(n, s)
    sim = NS(fo=f, f=f, prefix=np.array([queued], np.int64), start=np.zeros(K.K), hold=None, params=None, terrain=None)
    n._context = ((f, s, 20. + (f - HIT) / 60., False, True), sim, None, None)
    n.dispatch.frame = f
    monkeypatch.setattr(n, "queued_prefix", lambda *a: (queued, "fixture"))
    monkeypatch.setattr(AIR, "model_path", lambda sim_, plan, keys, game: NS(origin=f, commands=keys))
    monkeypatch.setattr(B2Geometry, "scan", lambda self, path: NS(complete=True, contacts=tuple(contacts)))
    forecast = NS(rs=NS(trk=NS(T=20., now={7: (None, None, NS(fam=None, t0=None)), 8: (None, None, NS(fam=None, t0=None))})))
    return BT.offer(n, forecast, prefs(target=l2)), s


@pytest.mark.parametrize("frame,owner,kind,kept", [
    (PRESS + 4, 7, "body", False),       # the strike's own contact, from its press
    (PRESS, 7, "move", False),
    (PRESS + 14, 7, "body", False),      # through B2's missed-strike window
    (PRESS + 15, 7, "body", True),
    (PRESS - 1, 7, "body", True),        # before the press nothing protects her: blocked
    (PRESS + 4, 8, "body", True),        # another owner
    (PRESS + 4, 7, "delayed", True),     # a delayed hazard of the target
    (PRESS + 4, None, "other", True),
])
def test_the_normal_knife_owns_only_its_targets_body_from_its_press(monkeypatch, frame, owner, kind, kept):
    n, _ = anchored(monkeypatch)
    offer, _ = tick(monkeypatch, n, HIT + 30, [PathContact(frame, owner, kind)])
    if kept:
        assert offer is None and n._bounce is None and n.commitment is None      # uncovered: B2 recovery
        assert n._failure_exposures[-1].move == MoveInstance(7, 946, "CC_SLAM")
    else:
        assert offer is not None and n._bounce is not None and n.commitment is not None
        assert offer.mask == int(BT.normal_keys()[32])                            # key for desired 32 (f + 2)


def test_l2_naming_another_target_changes_no_key_of_the_table(monkeypatch):
    n, _ = anchored(monkeypatch)
    masks = []
    for target in (7, 8):
        offer, s = tick(monkeypatch, n, HIT + 30, l2=target)
        masks.append((offer.mask, offer.move, offer.details["table_state"]))
        assert n.goal_preferences(s, prefs(target=target), handoff=True).target == target
    assert masks[0] == masks[1] == (int(BT.normal_keys()[32]), MoveInstance(7, 946, "CC_SLAM"), "baseline")
    assert n.commitment["bounce_table"] and not n._transfer_ready


def real_next_hit(n, hit=7, tail_state="Idle", f=PRESS + 3):
    """B2 observes the real next DownSlash hit + bounce on `hit`, with the table's strike pressed."""
    n._press = PRESS
    n._accepted = PRESS
    s = scene(f=f, target_state=tail_state, hit=hit)
    s["fc"] = FC + (f - HIT)
    BT.observe_frame(n, s)
    n._observe_application = lambda *a: None
    n.last_observed = f - 1
    n.observe(s)
    return s


@pytest.mark.parametrize("tail_state,pending", [("Slam 2", True), ("Slam Recover", False)])
def test_cross_target_at_the_real_next_hit_keeps_the_old_targets_identity_and_clock(monkeypatch, tail_state, pending):
    n, _ = anchored(monkeypatch)
    ta = n.commitment["ta"]
    s = real_next_hit(n, tail_state=tail_state)
    s["ents"][0]["colliders"] = [{"name": "Song Heavy Sentry", "enabled": True}]
    if pending:
        s["ents"][0]["colliders"].append({"name": "Slam Collider 1", "enabled": True})
    assert n.post_context is not None and n.commitment is None
    p2 = prefs(target=8)
    assert n.observe_bounce_goal(s, p2)
    goal = n._transfer_goal
    assert n._bounce is None                                                   # the table ended at this boundary
    assert (goal.target, goal.caster, goal.cast_fa, goal.cast_ta, goal.source_kind) == (8, 7, s["f"], ta, "BOUNCE")
    assert goal.responsibility == MoveInstance(7, 946, "CC_SLAM")               # never the new target's
    assert not any(e["event"] == "bounce_table_anchored" and e["frame"] == s["f"] for e in n.events)
    n._clock = ta + (s["f"] - 946) / 60.
    assert transfer.bounce_tail_pending(s, goal, n._clock) == pending
    n.goal_preferences(s, p2, handoff=True)
    assert n.post_context is None and n.runner.run is None                     # the old Run is abandoned, no key sent


def test_a_hit_on_the_other_clapper_never_releases_the_tables_commitment(monkeypatch):
    n, _ = anchored(monkeypatch)
    s = real_next_hit(n, hit=8)
    assert n._hit is None and n.post_context is None and n.commitment["bounce_table"]
    assert not n.observe_bounce_goal(s, prefs(target=8))                        # no bounce goal on a commitment
    assert n._bounce is not None and n._transfer_goal is None


def test_the_table_does_not_anchor_on_a_responsibility_of_the_other_clapper(monkeypatch):
    """o8 3267: a hit on the new target after a cross-target hand-off whose responsibility is still the old target's move.
    B2 reads hits and the target's life from commitment["move"]: the table would count hits on the wrong Clapper."""
    n = chain(monkeypatch)
    s = scene(hit=8)
    s["ents"][1]["fsms"][0]["state"] = "Slam Recover"
    BT.observe_frame(n, s)
    rt = MoveInstance(8, 960, "RUNE_TRANSFER")
    old = MoveInstance(7, 946, "CC_SLAM")
    n._hit = HIT
    n.post_context = {"move": rt, "bounce": HIT, "hit": HIT, "ta": 2.}
    n._transfer_responsibility[rt] = (old, 2.)
    assert n.observe_bounce_goal(s, prefs(target=8))
    assert n._bounce is None and n.commitment is None
    assert n._transfer_goal.responsibility == old and n._transfer_goal.caster == 8
    ev = [e for e in n.events if e["event"] == "bounce_table_not_anchored"]
    assert ev and "other Clapper" in ev[-1]["reason"]


def test_a_real_bounce_hands_off_a_script_run_left_from_before_the_chain_took_the_keys():
    from ssbot.combat.knife_chain_air import load_runner
    from ssbot.combat.knife_chain_air_native import NativeManualAirChain
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy as Policy
    n = NativeManualAirChain(runner_factory=load_runner, probe_ref="stale-script")
    n.reset(0, start_frame=999)
    n._clock_known = True
    n._clock = 20.
    s = scene(hit=7)
    move = MoveInstance(7, 946, "CC_SLAM")
    n._hit = HIT
    n.post_context = {"move": move, "bounce": HIT, "hit": HIT, "ta": 2.}
    p = Policy.__new__(Policy)
    p.chain_native = n
    aborted = []
    p.slam_play = NS(run=NS(phase="wait", bounced=False), abort=aborted.append)
    new = prefs(target=8)
    out = p._chain_goal_preferences(s, new, game_time=20.)
    assert out is not new and out.target == 8 and aborted == ["observed target transfer: goal handoff"]
    assert n.post_context is None and n._transfer_goal.source_kind == "BOUNCE" and n._transfer_goal.target == 8


def test_without_a_real_bounce_a_running_script_keeps_its_phase_gate():
    from ssbot.combat.knife_chain_air import load_runner
    from ssbot.combat.knife_chain_air_native import NativeManualAirChain
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy as Policy
    n = NativeManualAirChain(runner_factory=load_runner, probe_ref="stale-script")
    n.reset(0, start_frame=999)
    s = scene()
    s["ev"] = []
    p = Policy.__new__(Policy)
    p.chain_native = n
    aborted = []
    p.slam_play = NS(run=NS(phase="wait", bounced=False), abort=aborted.append)
    new = prefs(target=8)
    assert p._chain_goal_preferences(s, new, game_time=20.) is new and not aborted
