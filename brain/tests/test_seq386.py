"""Task 182 seq 312 #386 (the person 11-10, Sol seq 330: "锤后一律回中间，除非中间有大符文"; Sol REVIEW385 1-2: no landing proof gates the seam
strike or the vault; the entries still on the ordinary rows bind to the shared seam executor). L2 through its real entry
(tests/test_clapper_priority's scene), the chain's binding on its fixtures, the vault's air hand-back on the hero model."""
from dataclasses import replace
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import knife_chain_waypoint as WP
from ssbot.combat.tactics import clapper_plans as CP, clapper_separated as SEP
from ssbot.combat.tactics.modes import EntryAttack
from ssbot.core.worldstate import E
from tests.test_clapper_priority import change, manual, scene, step   # noqa: F401  (autouse manual-B fixture)
from tests.test_middle_return313 import hero_at, near_attack
from tests.test_separated312 import hit_on, slam, start, tick
from tests.test_seq385 import BODY, _antic, _hammers_over, _until, _vault_chain, _vault_sim


@pytest.fixture(autouse=True)
def plans_on(monkeypatch):
    monkeypatch.setattr(CP, "ENABLED", True)


def _move_f(ws, fc, x):
    """F (7) to root x, its body collider with it (the fixture's body is centred on the root)."""
    change(fc, 7, pos=(x, 4.))
    for e in ws.entities:
        if e.id == 7:
            xs = [px for px, _ in e.dmg_boxes[0].poly]
            dx = x - .5 * (min(xs) + max(xs))
            e.dmg_boxes[0].poly = [(px + dx, py) for px, py in e.dmg_boxes[0].poly]


# ---- L2: the way back after the slam (SeparatedSlam's post) ----

def test_every_branch_goes_back_into_the_middle_after_the_hammers():
    tac, ws, fc = start((20., 33.), 40.)                                         # N 32..34 too shallow for the strike: 1.2.3
    slam(tac, ws, fc, elapsed=0.)
    assert tac.last["clapper_sep_slam"]["branch"] == "1.2.3"
    out = _hammers_over(tac, ws, fc)
    post = tac.last["clapper_sep_slam"]
    assert post["phase"] == "post" and post["branch"] == "1.2.3" and post["now"]["tier"] == "fall" and post["now"]["between"] == 8
    assert out.waypoint is not None and out.waypoint.end == "past" and tac.last["clapper_winner"]["rule"] == "sep_slam"


def test_a_hit_or_a_tier_change_keeps_the_way_back_and_starts_a_new_action():
    tac, ws, fc, _ = _antic()
    _hammers_over(tac, ws, fc)
    a0 = tac.last["clapper_sep_slam"]["act_f"]
    hit_on(ws, 8); tick(tac, ws, fc); ws.events = []                              # a hit on N on the way: no end
    assert tac.last["clapper_sep_slam"]["phase"] == "post"
    _move_f(ws, fc, 30.5)                                                         # F walked in: 1 u apart, the seam tier
    out = tick(tac, ws, fc)
    post = tac.last["clapper_sep_slam"]
    assert post["now"]["tier"] == "seam" and post["act_f"] > a0 and post["act_log"][-1][2] == "tier seam"
    e = out.entry_attack                                                          # picked on the new action's first tick
    assert isinstance(e, EntryAttack) and (e.target, e.scope, e.event_f) == (8, "seam_slam", post["act_f"])
    assert out.strike_bound is not None and out.strike_bound[6] == "seam" and out.waypoint is None


def test_an_action_in_the_air_keeps_its_tier_until_she_lands_the_next_one_takes_tier_u():
    # sy21_seam 131537 / sy22_seam 131542: the slammer's evade took the gap past TIER_U mid-approach and dropped the action before its press
    tac, ws, fc, _ = _antic()
    _until(tac, ws, fc, 2)
    _move_f(ws, fc, 30.5)
    _hammers_over(tac, ws, fc)
    a0 = tac.last["clapper_sep_slam"]["act_f"]
    hero_at(ws, 36., y=8.); tick(tac, ws, fc)                                     # her approach in the air
    _move_f(ws, fc, 26.)                                                          # 5.5 u apart
    out = tick(tac, ws, fc)
    post = tac.last["clapper_sep_slam"]
    assert post["now"]["tier"] == "seam" and post["act_f"] == a0 and getattr(out.entry_attack, "scope", None) == "seam_slam"
    hero_at(ws, 36.); out = tick(tac, ws, fc)                                     # landed outside: a new action, TIER_U's tier
    post = tac.last["clapper_sep_slam"]
    assert post["now"]["tier"] == "fall" and post["act_f"] > a0 and out.entry_attack is None and out.waypoint is not None
    tac, ws, fc, _ = _antic()
    _until(tac, ws, fc, 2)
    _move_f(ws, fc, 30.5)
    _hammers_over(tac, ws, fc)
    _move_f(ws, fc, 28.5)                                                         # 3 u apart with her on the floor: TIER_U's tier
    tick(tac, ws, fc)
    assert tac.last["clapper_sep_slam"]["now"]["tier"] == "fall"


def test_its_seam_strike_meeting_a_body_or_her_landing_in_the_middle_ends_it():
    tac, ws, fc, _ = _antic()
    _until(tac, ws, fc, 2)
    _move_f(ws, fc, 30.5)
    _hammers_over(tac, ws, fc)
    hero_at(ws, 32.3, y=9.); hit_on(ws, 7); tick(tac, ws, fc); ws.events = []     # her down slash at the seam met F
    assert tac.last["clapper_sep_slam"] is None
    assert any(r["end"] == "after the slam: its seam strike met a body" for r in tac.last.get("clapper_releases") or [])
    tac, ws, fc, _ = _antic()                                                      # the fall tier: F 19..21, N 32.5..34.5
    _hammers_over(tac, ws, fc)
    hero_at(ws, 30., y=9.); tick(tac, ws, fc)                                      # over the middle, above the tops: goes on
    assert tac.last["clapper_sep_slam"]["phase"] == "post"
    hero_at(ws, 30., y=7.); tick(tac, ws, fc)                                      # dropped below the tops there (in the air): its
    assert tac.last["clapper_sep_slam"]["phase"] == "post"                         # fall slash's frames first
    hero_at(ws, 30., y=9.)                                                         # a hop does not restart them
    ends = []
    for _ in range(SEP.MIDDLE_HOLD_F):
        tick(tac, ws, fc)
        ends += [r["end"] for r in tac.last.get("clapper_releases") or []]
    assert tac.last["clapper_sep_slam"] is None and "after the slam: in the middle (in the air)" in ends


def test_a_live_big_rune_over_the_middle_postpones_the_way_back_until_it_is_over():
    tac, ws, fc, _ = _antic()
    change(fc, 7, state="Slam 2"); tick(tac, ws, fc)
    change(fc, 7, state="Slam Recover"); tick(tac, ws, fc)
    tac.rune_life = NS(live=lambda t: [NS(lo=24., hi=33.)])                      # a circle over her place in the middle
    out = tick(tac, ws, fc)
    post = tac.last["clapper_sep_slam"]
    assert post["phase"] == "post" and post["now"]["tier"] == "rune" and out.waypoint is None
    assert tac.last["clapper_winner"]["rule"] != "sep_slam"                       # the ordinary rules meanwhile, the intent kept
    tac.rune_life = NS(live=lambda t: [])
    out = tick(tac, ws, fc)
    assert tac.last["clapper_sep_slam"]["now"]["tier"] == "fall" and out.waypoint is not None and out.waypoint.end == "past"


def test_a_new_antic_ends_the_way_back():
    tac, ws, fc, _ = _antic()
    _hammers_over(tac, ws, fc)
    change(fc, 8, family=SEP.CC_CAST, state="Spell Antic", committed=True)
    tick(tac, ws, fc)
    assert (tac.last["clapper_sep_slam"] or {}).get("phase") != "post"
    assert any(r["end"] == "after the slam: a new antic (its own rules first)" for r in tac.last.get("clapper_releases") or [])


# ---- L2: the unseparated slam's return (MiddleReturn) ----

def test_a_slam_now_makes_the_return_due_wherever_she_was():
    tac, ws, fc = start((30., 44.), 15.)                                         # 7 slams 15 u from her: not near
    near_attack(tac, ws, fc)
    back = tac.last["clapper_back"]
    assert back is not None and back["move"] == [7, SEP.CC_SLAM] and tac.last["clapper_winner"]["rule"] == "back"


def test_a_live_big_rune_from_the_shared_ledger_holds_the_return():
    tac, ws, fc = start((30., 44.), 15.)
    tac.rune_life = NS(live=lambda t: [NS(lo=32., hi=42.)])                      # over the gap between the two
    near_attack(tac, ws, fc)
    assert tac.last["clapper_back"] is None and tac.last["clapper_winner"]["rule"] != "back"
    tac.rune_life = NS(live=lambda t: [])
    step(tac, ws, fc)
    assert tac.last["clapper_back"] is not None and tac.last["clapper_winner"]["rule"] == "back"   # still due: offered now


def test_the_return_seam_tier_binds_the_shared_seam_executor():
    tac, ws, fc = start((20., 24.), 15.)                                         # 2 u apart: the seam tier
    out = near_attack(tac, ws, fc)
    assert tac.last["clapper_scene"] == "middle return: seam strike"
    e, sb = out.entry_attack, out.strike_bound
    assert isinstance(e, EntryAttack) and (e.kind, e.source, e.source_family, e.scope) == ("stomp", 7, SEP.CC_SLAM, "seam_back")
    assert e.target == out.target and type(e.event_f) is int
    root = 20. if out.target == 7 else 24.
    assert sb == (out.target, pytest.approx(22.), pytest.approx(root), 1 if out.target == 7 else -1, e.event_f + SEP.POST_ACT_F,
                  None, "seam")
    assert out.target not in out.no_hit


def test_the_return_seam_entry_follows_tier_u_each_tick():
    # MiddleReturn keeps its existing pose switch: a gap opening past TIER_U turns it to the ground pose at once (its seam entry dropped:
    # the chain hands an approach not yet pressed back); only the slam's way back keeps an action's tier until she lands
    from tests.test_middle_return313 import move
    tac, ws, fc = start((20., 24.), 15.)
    e = near_attack(tac, ws, fc).entry_attack
    assert getattr(e, "scope", None) == "seam_back"
    hero_at(ws, 17., y=8.); out = step(tac, ws, fc)
    assert out.entry_attack == e
    move(ws, fc, 8, 25.)                                                          # 3 u apart
    out = step(tac, ws, fc)
    assert tac.last["clapper_scene"] != "middle return: seam strike" and getattr(out.entry_attack, "scope", None) != "seam_back"


# ---- the chain: the seam entries' binding ----

def test_a_seam_entry_binds_a_switch_goal_to_its_action_with_its_source_family():
    from ssbot.combat.knife_chain_commitment import MoveInstance
    from tests.test_knife_chain_transfer import cast_scene
    from tests.test_seq312_384 import _prefs
    from tests.test_target_entry_attack import native
    n, s = native(), cast_scene()
    s["ents"][0]["fsms"][0].update(state="Idle", t=.5)                          # the slam over: its source Idle
    entry = EntryAttack(8, "stomp", 7, SEP.CC_SLAM, 2., 10., scope="seam_slam", event_f=995)
    prefs = replace(_prefs(entry), strike_bound=(8, 36., 38., -1, 1115, None, "seam"))
    n.goal_preferences(s, prefs, handoff=True)
    g = n._transfer_goal
    assert g.source_kind == "SWITCH" and (g.target, g.caster) == (8, 7) and g.responsibility == MoveInstance(7, 995, "SEAM")
    assert n._seam_families[(7, 995)] == SEP.CC_SLAM and n._transfer_ready
    n.goal_preferences(s, prefs, handoff=True)
    assert n._transfer_goal is g                                                 # its action is bound once
    assert n._failure_exposure(MoveInstance(7, 995, "SEAM"), 1000, 1001, None).move == MoveInstance(7, 995, SEP.CC_SLAM)


def test_a_seam_bound_is_a_preference_the_stomp_stays_when_the_seam_side_is_out_of_reach():
    # sy23_seam 131555-131570: over N's outer half every row was turned down by the seam bound, the side key held back: she fell onto N
    from ssbot.combat.air_chain import ChainSim
    from ssbot.combat.knife_chain_commitment import MoveInstance
    from ssbot.combat.knife_chain_transfer import TransferGoal, propose
    from ssbot.knowledge import kinematics as K
    from tests.test_knife_chain_transfer import fit_pose, transfer_motion_scene
    r, s, oldsim = transfer_motion_scene(K.M_NORMAL)
    r.run = None
    s["f"] = 1040
    x = 47.3                                                                      # over 8's near part (root 48), falling
    s["hero"].update(pos=[x, 9.253], box=[x - .25, 7.7, x + .25, 9.779], vel=[0., -2.], silk=9, anim={"clip": "Airborne"},
                     can={"attack": True, "input": True})
    s["hero"]["tm"]["atk_cd"] = 0.
    fit_pose(s["ents"][1], state="Idle", x=48.)
    S = K.initial_state(oldsim.params, x, 9.253, vy=-2., ground=False)
    sim = ChainSim(S, np.array([0], np.int64), oldsim.hold, oldsim.params, oldsim.terrain, 1040, 1040)
    goal = TransferGoal(8, 7, 1040, 0., "SWITCH", MoveInstance(7, 1000, "SEAM"))
    seam = (51., 49.5, 1, 1100, None, "seam")                                     # its contact side 1.5 u past 8's root: out of reach
    made = propose(r, s, 0., sim, 8, False, np.zeros((0, 6)), set(), goal, bound=seam)
    assert made is not None and made[0].run.link == "strike" and made[0].run.v["seam_bound_fallback"] is True
    hard = propose(r, s, 0., sim, 8, False, np.zeros((0, 6)), set(), goal, bound=seam[:5] + ("outside",))
    assert hard is None or (hard[0].run.link != "strike" and not hard[0].run.v.get("seam_bound_fallback"))   # 1.2.2's stays hard


def test_the_seam_bound_fallback_never_takes_a_side_contact_from_beside_the_body():
    # sy24_seam 131518-131533: falling beside N below its top, the fallback's row met N's side low; the bounce's approach then met N
    from ssbot.combat import knife_chain_transfer as T
    from ssbot.combat.air_chain import ChainSim
    from ssbot.combat.knife_chain_commitment import MoveInstance
    from ssbot.knowledge import kinematics as K
    from tests.test_knife_chain_transfer import fit_pose, transfer_motion_scene
    r, s, oldsim = transfer_motion_scene(K.M_NORMAL)
    r.run = None
    s["f"] = 1040
    fit_pose(s["ents"][1], state="Idle", x=48.)
    body = T.body_box(s["ents"][1])
    x, y = float(body[0]) - .6, 6.6                                              # beside its near edge, her box bottom below its top
    s["hero"].update(pos=[x, y], box=[x - .25, y - 1.553, x + .25, y + .526], vel=[0., -4.], silk=9, anim={"clip": "Airborne"},
                     can={"attack": True, "input": True})
    s["hero"]["tm"]["atk_cd"] = 0.
    S = K.initial_state(oldsim.params, x, y, vy=-4., ground=False)
    sim = ChainSim(S, np.array([0], np.int64), oldsim.hold, oldsim.params, oldsim.terrain, 1040, 1040)
    goal = T.TransferGoal(8, 7, 1040, 0., "SWITCH", MoveInstance(7, 1000, "SEAM"))
    made = T.propose(r, s, 0., sim, 8, False, np.zeros((0, 6)), set(), goal, bound=(51., 49.5, 1, 1100, None, "seam"))
    assert made is None or (made[0].run.link != "strike" and not made[0].run.v["seam_bound_fallback"])


def test_the_held_bounce_after_the_hammers_hands_the_keys_to_l2s_vault_in_the_air(monkeypatch):
    # sy21_122 131517-131552: from the floor 1 u off N every vault row met N's floor growth; above its top in the air it cannot
    from tests.test_bounce_follow183 import Bout
    danger = ((25., 0., 34.5, 30.),)                                              # no clean middle landing
    vault = WP.WaypointGoal(31., 10 ** 6, "vault", 7, (("sep_post", 7, 1., 1), 0, "vault"), over=(34.61, 0., 38.2, 6.92),
                            family="CC_SLAM", over_iid=8, end="past")
    bout = Bout(monkeypatch, link='air', tail_done=True, danger=danger)
    bout.n._held_goal = bout.goal
    bout.prefs = replace(bout.prefs, waypoint=vault)
    assert bout.tick() is None and bout.n.runner.run is None and bout.n.commitment is None
    assert bout.n._held_goal is None and bout.n._transfer_goal is None
    assert bout.notes('transfer_follow_held_to_vault') and not bout.notes('transfer_follow_held')
    other = Bout(monkeypatch, link='air', tail_done=True, danger=danger)          # a vault over the other body: the drift goes on
    other.n._held_goal = other.goal
    other.prefs = replace(other.prefs, waypoint=replace(vault, over_iid=7))
    assert other.tick() is not None and other.notes('transfer_follow_held') and not other.notes('transfer_follow_held_to_vault')


# ---- the vault's air hand-back (knife_chain_waypoint end "past") ----

def _end_goal(f=1000):
    return WP.WaypointGoal(31.5, f + 200, "vault", 7, (("t", 7, 0.), 0, "vault"), over=BODY, family="CC_SLAM", over_iid=8, end="past")


@pytest.mark.parametrize("x", [23., 24., 24.6])
def test_vault_end_rows_hand_back_in_the_air_past_the_body_with_no_landing(x):
    from ssbot.knowledge import kinematics as K
    sim = _vault_sim(x)
    v = WP.vault_row(sim, _end_goal(), 1000)
    assert v is not None and v["land_k"] is None and v["land_box"] is None and v["takeoff_k"] is not None
    m = WP.SimRoller(sim)
    k, eb = v["end_k"], v["end_box"]
    assert eb[0] >= BODY[2] + WP.VAULT_PAD and not int(v["flags"][m.off + k]) & K.F_GROUND   # past the grown body, in the air
    g = (BODY[0] - WP.VAULT_PAD, BODY[1], BODY[2] + WP.VAULT_PAD, BODY[3] + WP.VAULT_PAD_TOP)
    way, fl = v["box"][m.off + 1:m.off + k + 1], v["flags"][m.off + 1:m.off + k + 1]
    hit = (way[:, 0] <= g[2]) & (way[:, 2] >= g[0]) & (way[:, 1] <= g[3]) & (way[:, 3] >= g[1]) & ((fl & K.F_INVULN) == 0)
    assert not hit.any()
    assert len(v["masks"]) == v["lock_k"] + 1 and v["lock_k"] >= k
    again = m.rollout(np.asarray(v["masks"], np.int64)[None])                    # the keys rolled again: the same hand-back box
    assert np.allclose(again.box[0, m.off + k], eb)


def test_the_vault_run_with_an_air_hand_back_ends_past_the_body_and_never_reads_a_landing(monkeypatch):
    from ssbot.combat.air_chain import ChainSim
    from ssbot.combat.holdfilter import hold_filter_jit
    from ssbot.combat.knife_chain_air import model_path
    from ssbot.combat.knife_chain_commitment import MoveInstance
    from ssbot.knowledge import kinematics as K
    from tests.test_l2_plan182 import PARAMS, TERRAIN, hero_state
    f = 1000
    S = hero_state(24.0)
    hold, prefix = K.HoldState.idle(1), 0
    sim = ChainSim(S, np.array([prefix], np.int64), hold, PARAMS, TERRAIN, f, f)
    chain, rs = _vault_chain(monkeypatch, sim, f)
    goal = WP.WaypointGoal(31.5, f + 120, "vault", 7, (("sep_post", 7, 1., f), 0, "vault"), over=BODY, family="CC_SLAM", over_iid=8,
                           end="past")
    prefs = NS(waypoint=goal)
    sent, past = [], None
    for _ in range(70):
        sim = ChainSim(S, np.array([prefix], np.int64), hold, PARAMS, TERRAIN, f, f)
        chain.queued_prefix = lambda frame, state: (int(prefix), None)
        box = sim.roll(np.zeros((1, 1), np.int64)).box[0, 0]
        state = {"f": f, "hero": {"hero_accepting_input": True, "pos": [float(S[K.PX]), float(S[K.PY])],
                                  "box": [float(v) for v in box]}}
        offer = chain._waypoint_offer(state, f / 60., sim, NS(rs=rs), prefs, ground=bool(S[K.GROUND] > 0))
        if offer is None:
            past = next((n for n in chain.notes if n["event"] == "waypoint_vault_past"), None)
            break
        chain.runner.run = offer.draft.run
        m = int(offer.mask)
        sent.append(m)
        nxt = model_path(sim, NS(iid=7, move=MoveInstance(7, f, "WAYPOINT"), origin=f, entry_k=0, press_k=None, contact_frame=None),
                         np.array([m], np.int64), f / 60.)
        S = nxt.states[:, 1].copy()
        hold = hold_filter_jit(np.array([[prefix]], np.int64), hold)[1]
        prefix, f = m, f + 1
    chosen = next(n for n in chain.notes if n["event"] == "waypoint_vault_chosen")
    assert chosen["end"] == "past" and chosen["start"] == "ground" and "no landing" in chosen["basis"]
    assert past is not None and past["box"][0] >= BODY[2] + WP.VAULT_PAD               # handed back in the air past the body
    assert chain.abandoned == ["waypoint vault past the body"] and not chain.recovered
    assert not any(n["event"] == "waypoint_vault_landed" for n in chain.notes)
