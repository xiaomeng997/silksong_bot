"""Task 181 (Sol seq 251, 253): the same-target bounce table / the real bounce under an L2 target change. The replay positives
are review181's (real L2, policy, planner, B2 geometry, before_send, sent); here the boundaries they and the review found.
- the normal knife is B2's ordinary strike: its own target's body on the way down is explained only by this knife's model
  contact on the actual start (ob_on 3183: uncovered at the press before this; R1: no blanket press..press+14);
- L2's target takes effect at the table's hand-back, the keys keep going until then; identities never mix;
- the chain's own real bounce of this STATE hands off from a script run left over from before the chain took the keys
  (wtb3 2760), an older post of the same Clapper does not (R2)."""
from dataclasses import dataclass
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import knife_chain_air as AIR
from ssbot.combat import knife_chain_bounce_table as BT
from ssbot.combat import knife_chain_transfer as transfer
from ssbot.combat import pogo_model as PM
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


@dataclass
class Path:
    origin: int
    commands: object
    box: object
    pos: object
    flags: object
    check_flags: object
    contact: object = None


def fake_paths(monkeypatch, f, *, hero_y=12., flags=None):
    """model_path on a plain falling box above the body: one row per frame from f (no real roll here)."""
    def model_path(sim_, plan, keys, game, *, contact=None):
        n = len(keys) + 2
        box = np.array([[29.75, hero_y, 30.25, hero_y + 2.]] * n)
        fl = np.zeros(n, np.int64) if flags is None else np.resize(flags, n)
        if contact is not None:
            fl = fl.copy()
            fl[contact + 1:] |= K.F_INVULN
        return Path(f, keys, box, box[:, :2], fl, fl.copy(), contact)
    monkeypatch.setattr(AIR, "model_path", model_path)


def tick(monkeypatch, n, f, plain=(), branch=(), l2=7, queued=0, witness=None):
    """One B2 tick of the anchored table at frame f: the geometry answers `plain` on the plain step, `branch` on its hit branch."""
    s = scene(f=f)
    s["ev"] = []
    BT.observe_frame(n, s)
    sim = NS(fo=f, f=f, prefix=np.array([queued], np.int64), start=np.zeros(K.K), hold=None, params=None, terrain=None)
    n._context = ((f, s, 20. + (f - HIT) / 60., False, True), sim, None, None)
    n.dispatch.frame = f
    monkeypatch.setattr(n, "queued_prefix", lambda *a: (queued, "fixture"))
    fake_paths(monkeypatch, f)
    monkeypatch.setattr(B2Geometry, "scan", lambda self, path: NS(complete=True, contacts=tuple(
        branch if path.contact is not None else plain)))
    monkeypatch.setattr(BT, "knife_witness", lambda *a: witness)
    forecast = NS(rs=NS(trk=NS(T=20., now={7: (None, None, NS(fam=None, t0=None)), 8: (None, None, NS(fam=None, t0=None))})))
    return BT.offer(n, forecast, prefs(target=l2)), s


def c(frame, owner=7, kind="body"):
    return PathContact(frame, owner, kind)


def blocked(n):
    return n._bounce is None and n.commitment is None and n._failure_exposures[-1].move == MoveInstance(7, 946, "CC_SLAM")


@pytest.mark.parametrize("contact,kind", [(PRESS + 4, "body"), (PRESS + 2, "move")])
def test_without_this_knifes_witness_its_own_target_blocks_as_before(monkeypatch, contact, kind):
    n, _ = anchored(monkeypatch)
    offer, _ = tick(monkeypatch, n, PRESS, [c(contact, kind=kind)], witness=None)
    assert offer is None and blocked(n)                                        # uncovered: B2 recovery keeps the exposure


@pytest.mark.parametrize("plain,hit_branch,through", [
    ([c(PRESS + 3)], [c(PRESS + 3)], True),                                    # the contact frame itself, buffered
    ([c(PRESS + 2, kind="move")], [c(PRESS + 2, kind="move")], True),          # two frames before it: the existing buffer
    ([c(PRESS + 4)], [], True),                                                # gone on the hit branch
    ([c(PRESS + 4)], [c(PRESS + 4)], True),                                    # still there, protected on the hit branch
    ([c(PRESS)], [c(PRESS)], False),                                           # before the buffer: not this knife's
    ([c(PRESS + 3)], [c(PRESS + 3), c(PRESS + 4, 8)], False),                  # another owner on the hit branch
    ([c(PRESS + 3), c(PRESS + 3, 8)], [c(PRESS + 3)], False),                  # another owner on the plain step
    ([c(PRESS + 3), c(PRESS + 3, kind="delayed")], [c(PRESS + 3)], False),     # a delayed hazard of the target
    ([c(PRESS + 3)], [c(PRESS + 3, kind="delayed")], False),
])
def test_a_witness_explains_only_the_contact_it_predicts(monkeypatch, plain, hit_branch, through):
    n, s = anchored(monkeypatch)
    monkeypatch.setattr(transfer, "body_box", lambda e: np.array([29., 3., 32., 7.]))
    offer, _ = tick(monkeypatch, n, PRESS, plain, hit_branch, witness=PRESS + 3)
    if through:
        assert offer is not None and n._bounce is not None
    else:
        assert offer is None and blocked(n)


def test_a_real_body_overlap_on_the_hit_branch_is_not_waived(monkeypatch):
    n, _ = anchored(monkeypatch)
    monkeypatch.setattr(transfer, "body_box", lambda e: np.array([29., 3., 32., 13.]))    # as high as her box in fake_paths
    offer, _ = tick(monkeypatch, n, PRESS, [c(PRESS + 3)], [c(PRESS + 3)], witness=PRESS + 3)
    assert offer is None and blocked(n)


def test_past_the_step_the_witness_only_buffers_the_plain_contacts(monkeypatch):
    n, _ = anchored(monkeypatch)
    monkeypatch.setattr(transfer, "body_box", lambda e: np.array([29., 3., 32., 7.]))
    offer, _ = tick(monkeypatch, n, PRESS - 3, [c(PRESS + 1)], witness=PRESS + 3)     # press + 3 lies past f + 4
    assert offer is not None
    n, _ = anchored(monkeypatch)
    offer, _ = tick(monkeypatch, n, PRESS - 3, [c(PRESS)], witness=PRESS + 3)
    assert offer is None and blocked(n)


def test_a_side_collision_before_the_contact_is_not_waived(monkeypatch):
    n, _ = anchored(monkeypatch)
    monkeypatch.setattr(transfer, "body_box", lambda e: np.array([29., 3., 32., 13.]))    # her box overlaps it already
    offer, _ = tick(monkeypatch, n, PRESS - 3, [c(PRESS + 1)], witness=PRESS + 3)         # the buffer alone would pass it
    assert offer is None and blocked(n)


# ---- the witness itself: geometry on a given path ------------------------------------------------------------------

def body_at(y_top):
    return np.array([29., 3., 32., y_top])


def witness(monkeypatch, f, *, hero_y, press=PRESS, accepted=PRESS, state="Idle", ev=None, top=7., flags=K.F_ATTACKING,
            body=True):
    n, _ = anchored(monkeypatch)
    table = n._bounce
    n._press, n._accepted = press, accepted
    if ev is not None:
        n._idle_ev[7] = ev
    fake_paths(monkeypatch, f, hero_y=hero_y, flags=np.array([flags]))
    monkeypatch.setattr(transfer, "contact_body_witness",
                        lambda e, frames, **kw: None if not body else np.tile(body_at(top), (frames, 1)))
    s = scene(f=f, target_state=state)
    sim = NS(fo=f, f=f, prefix=np.array([0], np.int64))
    return BT.knife_witness(n, table, sim, NS(), 20., s, s["ents"][0])


def reach():
    """The hero y at which every slash variant just reaches a body top 7 from above (hero at x 30)."""
    low = min(float(PM.slash_poly(face, alt)[:, 1].max()) for face in (-1, 1) for alt in (False, True))
    return 7. - low


def test_the_knife_meets_the_body_on_its_first_active_frame_ahead(monkeypatch):
    y = 8.
    w = witness(monkeypatch, PRESS + 1, hero_y=y)
    assert w == PRESS + PM.ACTIVE[0]
    assert witness(monkeypatch, PRESS + 5, hero_y=y) == PRESS + 6          # never this STATE, it showed no hit


@pytest.mark.parametrize("why,kw", [
    ("after its active window (a miss, then the body)", dict(f=PRESS + PM.ACTIVE[1], hero_y=8.)),
    ("too far above", dict(f=PRESS + 1, hero_y=30.)),
    ("not swinging", dict(f=PRESS + 1, hero_y=8., flags=0)),
    ("on the ground", dict(f=PRESS + 1, hero_y=8., flags=K.F_ATTACKING | K.F_GROUND)),
    ("no press sent", dict(f=PRESS + 1, hero_y=8., press=None, accepted=None)),
    ("another press", dict(f=PRESS + 1, hero_y=8., press=PRESS - 1)),
    ("not accepted, press passed", dict(f=PRESS + 1, hero_y=8., accepted=None)),
    ("no fitted pose", dict(f=PRESS + 1, hero_y=8., body=False)),
    ("an Idle hit since its entry", dict(f=PRESS + 1, hero_y=8., ev={"entry": HIT - 5, "buddy": True, "hit": HIT + 2})),
])
def test_no_witness(monkeypatch, why, kw):
    f = kw.pop("f")
    assert witness(monkeypatch, f, **kw) is None, why


def test_a_side_contact_early_in_the_swing_has_no_witness(monkeypatch):
    # press + 1: the swing's first active frame is press + 3, and beside the body no variant meets it
    n, _ = anchored(monkeypatch)
    n._press, n._accepted = PRESS, PRESS
    def model_path(sim_, plan, keys, game, *, contact=None):
        k = len(keys) + 2
        box = np.array([[33.5, 4., 34., 6.]] * k)                         # level with the body, 1.5 u beside it
        return Path(PRESS + 1, keys, box, box[:, :2], np.full(k, K.F_ATTACKING), np.full(k, K.F_ATTACKING))
    monkeypatch.setattr(AIR, "model_path", model_path)
    monkeypatch.setattr(transfer, "contact_body_witness", lambda e, frames, **kw: np.tile(body_at(7.), (frames, 1)))
    s = scene(f=PRESS + 1)
    sim = NS(fo=PRESS + 1, f=PRESS + 1, prefix=np.array([0], np.int64))
    assert BT.knife_witness(n, n._bounce, sim, NS(), 20., s, s["ents"][0]) is None


# ---- L2's target and identities ---------------------------------------------------------------------------------------

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


# ---- the hand-off from a left-over script run ---------------------------------------------------------------------------

def policy_with(n):
    from ssbot.train.forum_planner_policy import ForumPlannerPolicy as Policy
    p = Policy.__new__(Policy)
    p.chain_native = n
    aborted = []
    p.slam_play = NS(run=NS(phase="wait", bounced=False), abort=aborted.append)
    return p, aborted


def native():
    from ssbot.combat.knife_chain_air import load_runner
    from ssbot.combat.knife_chain_air_native import NativeManualAirChain
    n = NativeManualAirChain(runner_factory=load_runner, probe_ref="stale-script")
    n.reset(0, start_frame=999)
    n._clock_known = True
    n._clock = 20.
    return n


MOVE = MoveInstance(7, 946, "CC_SLAM")


def test_a_real_bounce_hands_off_a_script_run_left_from_before_the_chain_took_the_keys():
    n = native()
    s = scene(hit=7)
    n._hit = HIT
    n.post_context = {"move": MOVE, "bounce": HIT, "hit": HIT, "press": HIT - 5, "ta": 2.}
    p, aborted = policy_with(n)
    new = prefs(target=8)
    out = p._chain_goal_preferences(s, new, game_time=20.)
    assert out is not new and out.target == 8 and aborted == ["observed target transfer: goal handoff"]
    assert n.post_context is None and n._transfer_goal.source_kind == "BOUNCE" and n._transfer_goal.target == 8


@pytest.mark.parametrize("post", [
    {"bounce": HIT - 20, "hit": HIT - 20, "press": HIT - 28},       # an older post of the same Clapper, a new hit this STATE
    {"bounce": HIT, "hit": None, "press": HIT - 5},                 # no strike hit (hook bounce shape)
    {"bounce": HIT, "hit": HIT, "press": None},                     # no press of this strike
    {"bounce": HIT, "hit": HIT - 9, "press": HIT - 5},              # the hit before this strike's press
])
def test_only_this_states_bounce_of_this_strike_opens_the_script_bypass(post):
    n = native()
    s = scene(hit=7)                                                # a separate current DownSlash hit on the same Clapper
    n._hit = post["hit"]
    n.post_context = {"move": MOVE, "ta": 2., **post}
    p, aborted = policy_with(n)
    new = prefs(target=8)
    assert p._chain_goal_preferences(s, new, game_time=20.) is new and not aborted
    assert n.post_context is not None                               # nothing consumed by this tick's goal step


def test_the_after_phase_handoff_is_unchanged():
    n = native()
    s = scene(hit=7)
    n._hit = HIT - 20
    n.post_context = {"move": MOVE, "ta": 2., "bounce": HIT - 20, "hit": HIT - 20, "press": HIT - 28}
    p, aborted = policy_with(n)
    p.slam_play.run = NS(phase="after", bounced=False, iid=7, fa=946, ta=2.)
    out = p._chain_goal_preferences(s, prefs(target=8), game_time=20.)
    assert out.target == 8 and aborted == ["observed target transfer: goal handoff"]


def test_without_a_real_bounce_a_running_script_keeps_its_phase_gate():
    n = native()
    s = scene()
    s["ev"] = []
    p, aborted = policy_with(n)
    new = prefs(target=8)
    assert p._chain_goal_preferences(s, new, game_time=20.) is new and not aborted
