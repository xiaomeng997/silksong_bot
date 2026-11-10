"""Task 182 seq 312 #385 (Sol REVIEW384 1-4; the person 11-10: 1.2.2 side slashes, then the down slash on N's outer part outside the range
before N unlocks, the bounce held off N's outer edge over the hammers, then over N into the middle; N evading: outside the range until the
slam is over; Sol seq 326: every chosen return into the middle with the two at most 2.5 u apart is one down slash aligned with the seam).
L2 through its real entry (tests/test_clapper_priority's scene), the vault row on the hero model, the chain's pieces on their fixtures."""
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat import knife_chain_transfer as T, knife_chain_waypoint as WP
from ssbot.combat.tactics import clapper_plans as CP, clapper_separated as SEP
from ssbot.combat.tactics.modes import EntryAttack
from ssbot.core.worldstate import E
from tests.test_clapper_priority import change, manual, scene, step   # noqa: F401  (autouse manual-B fixture)
from tests.test_middle_return313 import hero_at
from tests.test_separated312 import cast, end_rune, hit_on, slam, start, tick


@pytest.fixture(autouse=True)
def plans_on(monkeypatch):
    monkeypatch.setattr(CP, "ENABLED", True)


def _down_hit(ws, iid):
    from ssbot.core.worldstate import Ev
    ws.events = [NS(kind=Ev.HIT_DEALT, data=NS(target_id=iid, attack="Nail", src="DownSlash"))]


def _antic(xs=(20., 33.5), hx=40.):
    """F 7 at 20 slams toward her (40), N 8 at 33.5 (body 32.5..34.5) across the range edge 32.76: 1.2.2; its antic clock from 0."""
    tac, ws, fc = start(xs, hx)
    ws.hero.contact = E("GROUND")
    out = slam(tac, ws, fc, elapsed=0.)
    return tac, ws, fc, out


def _until(tac, ws, fc, k):
    f0 = tac.last["clapper_sep_slam"]["antic_f"]
    out = None
    while ws.stamp.frame < f0 + k:
        out = tick(tac, ws, fc)
    return out


def _hammers_over(tac, ws, fc):
    change(fc, 7, state="Slam 2"); tick(tac, ws, fc)
    change(fc, 7, state="Slam Recover"); tick(tac, ws, fc)
    return tick(tac, ws, fc)


# ---- 1.2.2: the antic's stages ----

def test_1_2_2_side_settle_strike_wait_follow_the_antic_clock():
    tac, ws, fc, out = _antic()
    sep = tac.last["clapper_sep_slam"]
    assert sep["branch"] == "1.2.2" and sep["mode"] == "side" and out.entry_attack is None and out.strike_bound is None
    assert out.stance_x == pytest.approx(34.5 + .25 + SEP.SIDE_GAP_U)          # just off N's outer edge, outside the range
    assert 7 in out.no_hit and 8 not in out.no_hit and 8 in out.no_pogo and 8 in out.ground_hit
    assert out.hit_kw[8][0] > 0 and out.hit_kw[8][1:] == (0., 0., 0.)           # side slashes only, from the floor
    out = _until(tac, ws, fc, SEP.SIDE_LAST_F + 1)
    assert tac.last["clapper_sep_slam"]["mode"] == "settle" and {7, 8} <= out.no_hit and out.entry_attack is None
    out = _until(tac, ws, fc, SEP.STRIKE_OPEN_F)
    sep = tac.last["clapper_sep_slam"]
    e, sb = out.entry_attack, out.strike_bound
    assert sep["mode"] == "strike" and isinstance(e, EntryAttack) and (e.target, e.kind, e.source, e.scope) == (8, "stomp", 7, "sep_slam")
    f0 = sep["antic_f"]
    assert sb[0] == 8 and sb[1] == pytest.approx(34.5 - SEP.STRIKE_DEPTH_U) and sb[2] == pytest.approx(20. + SEP.SLAM_EDGE_U + .5)
    assert sb[3:] == (1, f0 + SEP.LOCK_LAST_F, SEP.STRIKE_JUMP_HOLD, "outside")
    assert (sb[1] - sb[2]) * sb[3] >= 0                                          # the aim itself is outside the bound
    out = _until(tac, ws, fc, SEP.LOCK_LAST_F + 1)
    assert tac.last["clapper_sep_slam"]["mode"] == "wait" and out.entry_attack is None and out.strike_bound is None
    assert {7, 8} <= out.no_hit and out.hold_over == frozenset({8})


def test_side_hits_leave_the_strike_and_the_down_slash_ends_it():
    tac, ws, fc, _ = _antic()
    hit_on(ws, 8); tick(tac, ws, fc); ws.events = []                            # a side slash on the locked N (k 1)
    sep = tac.last["clapper_sep_slam"]
    assert sep["near_hit"] is not None and sep["strike_hit"] is None
    out = _until(tac, ws, fc, SEP.STRIKE_OPEN_F)
    assert out.entry_attack is not None and out.entry_attack.target == 8
    _down_hit(ws, 8); out = tick(tac, ws, fc); ws.events = []                   # the strike window's down slash meets N
    sep = tac.last["clapper_sep_slam"]
    assert sep["strike_hit"] is not None and sep["mode"] == "wait" and out.entry_attack is None
    assert out.hold_over == frozenset({8}) and {7, 8} <= out.no_hit             # its bounce held, no new hit on N


def test_n_too_shallow_outside_the_range_for_a_strike_with_its_margin_is_1_2_3():
    tac, ws, fc = start((20., 33.), 40.)                                        # N 32..34: 0.74 u past the bound 33.26
    out = slam(tac, ws, fc, elapsed=0.)
    sep = tac.last["clapper_sep_slam"]
    assert sep["branch"] == "1.2.3" and sep["shallow_122"] == pytest.approx(.74) and out.entry_attack is None
    assert out.stance_x == pytest.approx(20. + SEP.SLAM_EDGE_U + SEP.OUT_U)


def test_n_evading_in_1_2_2_waits_outside_the_range_then_still_goes_back_into_the_middle():
    tac, ws, fc, _ = _antic()
    change(fc, 8, state="Evade Scuttle")
    out = tick(tac, ws, fc)
    sep = tac.last["clapper_sep_slam"]
    assert sep["mode"] == "wait" and sep["near_evaded"] is not None and {7, 8} <= out.no_hit
    assert out.stance_x == pytest.approx(20. + SEP.SLAM_EDGE_U + SEP.OUT_U)       # just outside the range edge, no chase
    change(fc, 8, state="Idle")
    out = _until(tac, ws, fc, SEP.STRIKE_OPEN_F)
    assert tac.last["clapper_sep_slam"]["mode"] == "wait" and out.entry_attack is None and out.strike_bound is None
    out = _hammers_over(tac, ws, fc)
    # #386 (the person 11-10, Sol seq 330): the evade is kept for the record, the way back goes on (over N, the fall tier)
    post = tac.last["clapper_sep_slam"]
    assert post["phase"] == "post" and post["near_evaded"] is not None and post["now"]["tier"] == "fall"
    assert out.waypoint is not None and out.waypoint.kind == "vault" and out.waypoint.end == "past"


# ---- 1.2.2 after both hammers: the move over N apart from the strike's eligibility ----

def test_after_both_hammers_n_struck_still_takes_the_vault_over_it_into_the_middle():
    tac, ws, fc, _ = _antic()
    _until(tac, ws, fc, SEP.STRIKE_OPEN_F)
    _down_hit(ws, 8); tick(tac, ws, fc); ws.events = []
    out = _hammers_over(tac, ws, fc)
    post = tac.last["clapper_sep_slam"]
    assert post["phase"] == "post" and post["strike_hit"] is not None and out.entry_attack is None
    wp = out.waypoint
    assert wp is not None and (wp.kind, wp.source, wp.family, wp.over_iid) == ("vault", 7, "CC_SLAM", 8)
    assert wp.over == pytest.approx((min(32.5, 33.5 - CP.BODY_HALF), 0., max(34.5, 33.5 + CP.BODY_HALF), CP.BODY_TOP))
    # #386 (Sol REVIEW385 1): no landing band: the route ends at its air hand-back point past N
    assert wp.land is None and wp.end == "past" and 21. < wp.x < 32.5             # her place in the middle between F (19..21) and N
    assert wp.by_f == post["act_f"] + SEP.POST_ACT_F and wp.plan[0][-1] == post["act_f"]
    assert out.stance_x == pytest.approx(32.5 - SEP.FALL_U - .25) and 7 in out.no_hit
    again = tick(tac, ws, fc)
    assert again.waypoint.plan == wp.plan                                       # one stable place: the Run is not withdrawn
    hero_at(ws, 31., y=9.)                                                      # past N's inner edge, not its passed box (#386), above the tops
    out = tick(tac, ws, fc)
    assert out.waypoint is not None and 8 not in out.no_hit                     # the vault's own hand-back test; her slash on N counts
    hero_at(ws, 30.5, y=9.)                                                     # past the box (root - 2.25) by her half width + pad
    out = tick(tac, ws, fc)
    assert tac.last["clapper_sep_slam"]["phase"] == "post" and out.waypoint is None


def test_a_landing_on_her_side_of_n_keeps_the_way_over_it_and_one_in_the_middle_ends_it():
    tac, ws, fc, _ = _antic()
    _until(tac, ws, fc, SEP.STRIKE_OPEN_F)
    _down_hit(ws, 8); tick(tac, ws, fc); ws.events = []
    ws.hero.contact = E("AIR")                                                   # up from the bounce, held off N over the hammers
    first = _hammers_over(tac, ws, fc).waypoint
    assert tac.last["clapper_sep_slam"]["phase"] == "post"
    ws.hero.contact = E("GROUND")                                                # the hold lands on her side (40): the post goes on
    out = tick(tac, ws, fc)
    post = tac.last["clapper_sep_slam"]
    assert post["phase"] == "post" and post["act_log"][-1][2] == "landed outside the middle"
    assert out.waypoint is not None and out.waypoint.kind == "vault" and out.waypoint.plan != first.plan   # a new action: its own key
    ws.hero.contact = E("AIR"); tick(tac, ws, fc)                                # the vault's jump ...
    hero_at(ws, 31.); ws.hero.contact = E("GROUND")                              # ... lands in the middle: done
    tick(tac, ws, fc)
    assert tac.last["clapper_sep_slam"] is None


@pytest.mark.parametrize("froot,gap,seam", [(30.5, 1., 32.), (31., .5, 32.25), (31.5, 0., 32.5), (32., -.5, 32.75)])
def test_the_post_with_the_two_at_most_2_5_u_apart_is_the_seam_strike_with_no_landing_gate(froot, gap, seam):
    # Sol REVIEW385 (ROOT_PROBES385: gaps .5 / 0 / -.5 had no action, the vault's landing band in the seam gating it): #386: the seam tier
    # is the shared seam strike's chain stomp on N (its entry, the strike bounded to the seam), no vault and no landing anywhere
    tac, ws, fc, _ = _antic()
    _until(tac, ws, fc, 2)
    change(fc, 7, pos=(froot, 4.))                                               # F lunged: its body froot -+ 1, N 32.5..34.5
    for e in ws.entities:
        if e.id == 7:
            e.dmg_boxes[0].poly = [(x - 20. + froot, y) for x, y in e.dmg_boxes[0].poly]
    out = _hammers_over(tac, ws, fc)
    post = tac.last["clapper_sep_slam"]
    now = post["now"]
    assert post["phase"] == "post" and now["tier"] == "seam" and now["seam"] == pytest.approx(seam) and now["gap"] == pytest.approx(gap)
    assert tac.last["clapper_scene"] == "separated slam 1.2.2 after: seam strike" and out.stance_x == pytest.approx(seam)
    assert out.waypoint is None                                                  # no vault, no landing band
    e, sb = out.entry_attack, out.strike_bound
    assert isinstance(e, EntryAttack) and (e.target, e.kind, e.source, e.scope, e.event_f) == (8, "stomp", 7, "seam_slam", post["act_f"])
    assert sb == (8, pytest.approx(seam), pytest.approx(33.5), -1, post["act_f"] + SEP.POST_ACT_F, None, "seam")
    assert not ({7, 8} & out.no_hit) and out.hit_kw[8][:3] == (0., 0., 0.) and out.hit_kw[8][3] > 0   # the rows: down slashes only
    hero_at(ws, seam, y=9.)                                                      # over the seam (above the tops), past N's root
    out = tick(tac, ws, fc)
    assert not ({7, 8} & out.no_hit) and out.hit_kw[8][3] > 0 and out.hit_kw[8][0] == 0.   # both credited, down slashes only


# ---- the shared small-gap rule (Sol seq 326) ----

@pytest.mark.parametrize("xs,ok,seam", [((20., 24.5), True, 22.25), ((20., 24.51), False, 22.255), ((20., 21.), True, 20.5)])
def test_the_shared_small_gap_rule_is_one_value_at_2_5_u(xs, ok, seam):
    from ssbot.combat.tactics.clapper_scene import geometry
    tac, ws, fc = start(xs, 10.)
    geo = geometry(tac, ws, list(fc.subjects))
    small, x, gap = SEP.seam_return(geo)
    assert small is ok and x == pytest.approx(seam)
    assert T.small_gap(NS(width=gap)) is ok                                      # the chain reads the same value


def test_overhead_and_back_take_the_seam_strike_with_uneven_tops():
    from tests.test_separated312 import top
    from tests.test_middle_return313 import near_attack
    tac, ws, fc = start((20., 21.5), 20.75)                                      # tight, overlapping
    top(ws, 8, 8.2)
    tick(tac, ws, fc)
    assert tac.last["clapper_scene"] == "tight middle: seam strike"
    tac, ws, fc = start((20., 24.), 15.)                                         # outside, 2 u apart (a standable gap: no #379 gate)
    top(ws, 8, 8.2)
    out = near_attack(tac, ws, fc)
    assert tac.last["clapper_scene"] == "middle return: seam strike" and out.stance_x == pytest.approx(22.)
    assert not ({7, 8} & out.no_hit) and out.hit_kw[out.target][3] > 0


def test_the_small_rune_end_seam_tier_binds_the_chain_to_the_seam():
    tac, ws, fc = start((20., 23.), 15.)
    cast(tac, ws, fc, 7)
    out = end_rune(tac, ws, fc, 7)
    a = tac.last["clapper_rune_after"]
    e, sb = out.entry_attack, out.strike_bound
    assert a["tier"] == "seam" and getattr(e, "scope", None) == "rune_end"
    t = 7 if a["target"] == 7 else 8
    root = 20. if t == 7 else 23.
    assert sb[0] == t and sb[1] == pytest.approx(21.5) and sb[2] == pytest.approx(root) and sb[3] == (1 if t == 7 else -1)
    assert sb[4] == a["f0"] + int(round(SEP.POST_S * 60)) and sb[5] is None and sb[6] == "seam"


# ---- the vault row (knife_chain_waypoint.vault_row) on the hero model ----

def _vault_sim(x, y=4.568, ground=True):
    from ssbot.combat.air_chain import ChainSim
    from ssbot.knowledge import kinematics as K
    from tests.test_l2_plan182 import PARAMS
    act = {"hf": {"latched": 0, "desired": 0, "pending": [0] * 22, "age": [100] * 22}}
    S = K.initial_state(PARAMS, x, y, vx=0., mode=K.M_NORMAL, ground=ground)
    return ChainSim(S, np.array([0], np.int64), K.HoldState.from_act(act), PARAMS, K.Terrain2D.from_boxes([(-100., -10., 100., 3.015)]),
                    1000, 1000)


BODY = (25.33, 0., 29.83, 6.92)


def _vault_goal(x=31.5, band=(30.6, 33.5)):
    return WP.WaypointGoal(x, 1200, "vault", 7, (("t", 7, 0.), 0, "vault"), over=BODY, family="CC_SLAM", over_iid=8, land=band)


@pytest.mark.parametrize("x", [23., 24., 24.6])
def test_vault_row_clears_an_idle_body_from_the_floor_and_lands_in_the_band(x):
    from ssbot.knowledge import kinematics as K
    sim = _vault_sim(x)
    v = WP.vault_row(sim, _vault_goal(), 1000)
    assert v is not None and v["takeoff_k"] is not None
    lb = v["land_box"]
    assert 30.6 <= .5 * (lb[0] + lb[2]) <= 33.5
    box, fl = v["box"], v["flags"]
    m = WP.SimRoller(sim)
    g = (BODY[0] - WP.VAULT_PAD, BODY[1], BODY[2] + WP.VAULT_PAD, BODY[3] + WP.VAULT_PAD_TOP)
    way = box[m.off + 1:]
    hit = (way[:, 0] <= g[2]) & (way[:, 2] >= g[0]) & (way[:, 1] <= g[3]) & (way[:, 3] >= g[1]) & ((fl[m.off + 1:] & K.F_INVULN) == 0)
    assert not hit.any()
    # the keys are the row the model rolled: rolled again they land on the same frame and place
    again = m.rollout(np.asarray(v["masks"] + [0] * 8, np.int64)[None])
    t, j = WP._air_index(np.asarray(again.flags[0]), m.off)
    assert j - m.off == v["land_k"] and np.allclose(again.box[0, j], lb)
    # the alternatives: at most VAULT_ALTS, one per landing place, in the same order (nearer the place first), each in the band
    lands = [.5 * (c["land_box"][0] + c["land_box"][2]) for c in [v] + v["alts"]]
    assert 1 <= len(lands) <= WP.VAULT_ALTS + 1 and len({round(x, 1) for x in lands}) == len(lands)
    assert [abs(x - 31.5) for x in lands] == sorted(abs(x - 31.5) for x in lands) and all(30.6 <= x <= 33.5 for x in lands)


def test_vault_row_none_once_past_the_body_or_without_one():
    assert WP.vault_row(_vault_sim(30.5), _vault_goal(), 1000) is None           # past the far edge already
    assert WP.vault_row(_vault_sim(24.), WP.WaypointGoal(31.5, 1200, "vault", 7, ((1, 0.), 0, "vault")), 1000) is None


# ---- the vault Run (knife_chain_air_native._vault_offer) in closed loop on the hero model and a real support ----

def _vault_chain(monkeypatch, sim, f, body=None):
    from dataclasses import asdict  # noqa: F401
    from ssbot.combat import knife_chain_air_native as AN
    from tests.test_l2_plan182 import _bomb_support
    cls = next(c for c in vars(AN).values() if isinstance(c, type) and "_waypoint_offer" in vars(c))
    monkeypatch.setattr(AN, "complete_hf", lambda state: True)
    from ssbot.combat.knife_chain_eval import Run
    monkeypatch.setattr(AN, "logical_copy", lambda r: NS(run=Run(r.run.chain, r.run.link, dict(r.run.v))))
    chain = object.__new__(cls)
    chain.notes, chain.recovered, chain.abandoned = [], [], []
    chain._note = lambda ev, **kw: chain.notes.append(dict(event=ev, **kw))
    chain._recover = lambda why, frame: chain.recovered.append((why, frame))
    chain._abandon = lambda why: chain.abandoned.append(why)
    chain.runner = NS(run=None, fork_empty=lambda anchor: NS(run=None))
    chain._waypoint_failed, chain._waypoint_declined, chain._waypoint_responsibility, chain._vault_tried = set(), None, {}, {}
    chain._locked_mode = lambda sim: None
    rs = _bomb_support(owner=7, body=body)
    return chain, rs


def test_the_vault_run_starts_follows_its_row_and_hands_back_past_the_body(monkeypatch):
    from ssbot.combat.air_chain import ChainSim
    from ssbot.combat.knife_chain_air import model_path
    from ssbot.knowledge import kinematics as K
    from tests.test_l2_plan182 import PARAMS, TERRAIN, hero_state
    f = 1000
    S = hero_state(24.0)
    hold, prefix = K.HoldState.idle(1), 0
    sim = ChainSim(S, np.array([prefix], np.int64), hold, PARAMS, TERRAIN, f, f)
    chain, rs = _vault_chain(monkeypatch, sim, f)
    goal = WP.WaypointGoal(31.5, f + 120, "vault", 7, (("sep_post", 7, 1.), 0, "vault"), over=BODY, family="CC_SLAM", over_iid=8,
                           land=(30.6, 33.5))
    prefs = NS(waypoint=goal)
    sent, past = [], None
    for k in range(70):
        sim = ChainSim(S, np.array([prefix], np.int64), hold, PARAMS, TERRAIN, f, f)
        chain.queued_prefix = lambda frame, state: (int(prefix), None)
        box = sim.roll(np.zeros((1, 1), np.int64)).box[0, 0]
        ground = bool(S[K.GROUND] > 0)
        state = {"f": f, "hero": {"hero_accepting_input": True, "pos": [float(S[K.PX]), float(S[K.PY])],
                                  "box": [float(v) for v in box]}}
        offer = chain._waypoint_offer(state, f / 60., sim, NS(rs=rs), prefs, ground=ground)
        if offer is None:
            past = next((n for n in chain.notes if n["event"] == "waypoint_vault_past"), None)
            break
        chain.runner.run = offer.draft.run
        m = int(offer.mask)
        sent.append(m)
        from ssbot.combat.knife_chain_commitment import MoveInstance
        step = model_path(sim, NS(iid=7, move=MoveInstance(7, f, "WAYPOINT"), origin=f, entry_k=0, press_k=None, contact_frame=None),
                          np.array([m], np.int64), f / 60.)
        S = step.states[:, 1].copy()
        from ssbot.combat.holdfilter import hold_filter_jit
        hold = hold_filter_jit(np.array([[prefix]], np.int64), hold)[1]
        prefix, f = m, f + 1
    chosen = next(n for n in chain.notes if n["event"] == "waypoint_vault_chosen")
    assert chosen["start"] == "ground" and chosen["rank"] == 0 and 30.6 <= chosen["land_x"] <= 33.5
    assert past is not None and past["box"][0] >= BODY[2] + WP.VAULT_PAD               # her box past the body, in the air
    assert chain.abandoned == ["waypoint vault past the body"] and not chain.recovered
    assert any(m & K.B_JUMP for m in sent) and any(m & K.B_RIGHT for m in sent)


def test_a_vault_whose_every_landing_is_covered_is_declined_with_each_rows_reason(monkeypatch):
    from ssbot.combat.air_chain import ChainSim
    from ssbot.knowledge import kinematics as K
    from tests.test_l2_plan182 import PARAMS, TERRAIN, hero_state
    f = 1000
    sim = ChainSim(hero_state(24.0), np.zeros(1, np.int64), K.HoldState.idle(1), PARAMS, TERRAIN, f, f)
    chain, rs = _vault_chain(monkeypatch, sim, f, body=(30.0, 3.0, 34.0, 6.0))     # another enemy over the whole band
    chain.queued_prefix = lambda frame, state: (0, None)
    goal = WP.WaypointGoal(31.5, f + 120, "vault", 7, (("sep_post", 7, 1.), 0, "vault"), over=BODY, family="CC_SLAM", over_iid=8,
                           land=(30.6, 33.5))
    state = {"f": f, "hero": {"hero_accepting_input": True, "pos": [24.0, 4.568], "box": [23.75, 3.015, 24.25, 5.09]}}
    assert chain._waypoint_offer(state, f / 60., sim, NS(rs=rs), NS(waypoint=goal), ground=True) is None
    note = next(n for n in chain.notes if n["event"] == "waypoint_rejected")
    assert note["reason"] == "no clean row" and len(note["rows"]) == 1 + WP.VAULT_ALTS
    assert all(r["reason"] == "route blocked" and r["first"]["owner_iid"] == 100 for r in note["rows"])
    # the same scene: no second search on the next tick (event-limited)
    chain.notes.clear()
    assert chain._waypoint_offer(dict(state, f=f), f / 60., sim, NS(rs=rs), NS(waypoint=goal), ground=True) is None
    assert not any(n["event"] == "waypoint_rejected" for n in chain.notes)


# ---- the chain: the hold's drift and the strike bound's kinds ----

def test_the_held_follow_up_drifts_off_the_bounced_bodys_outer_edge(monkeypatch):
    # 8 bounced her over its body (her centre 37.821, its root 36.86), the other one 7 at 24.1 on its inner side: held, the side key goes
    # outward (right) to HOLD_OUT_U off 8's outer edge, never the seam aim toward 7; unheld, the Task 183 follow-up aims at the middle
    from ssbot.combat.knife_chain_format import MASK_NAMES as B
    from tests.test_bounce_follow183 import Bout
    bout = Bout(monkeypatch, link='air', tail_done=True)
    sim = bout.sim()
    s = bout.state(sim)
    body = T.body_box(bout.ents[1])
    assert body[0] < s["hero"]["pos"][0] < body[2] - T.HOLD_OUT_U
    held = T.propose(bout.n.runner, s, bout.game, sim, 8, False, np.zeros((0, 6)), set(), bout.goal, hold_over=True, no_strike=True)
    free = T.propose(bout.n.runner, s, bout.game, sim, 8, False, np.zeros((0, 6)), set(), bout.goal)
    assert held[0].run.v["side"] == B["R"] and held[0].run.v["hold_over"] is True and held[0].run.v["seam_inner"] is None
    assert free[0].run.v["side"] != B["R"]
    s["hero"]["pos"][0] = body[2] + T.HOLD_OUT_U                                 # there: no side key
    held = T.propose(bout.n.runner, s, bout.game, sim, 8, False, np.zeros((0, 6)), set(), bout.goal, hold_over=True, no_strike=True)
    assert held[0].run.v["side"] == 0


def test_the_held_bounce_after_both_hammers_takes_a_clean_middle_or_drifts_on(monkeypatch):
    # L2's 1.2.2 hold is over (no hold_over now) but the bounce goal is the held one: a clean middle landing when one exists, otherwise
    # the drift off the bounced body goes on (away from the other one), never the seam approach across it, never a new strike
    from ssbot.combat.knife_chain_format import MASK_NAMES as B
    from tests.test_bounce_follow183 import Bout
    bout = Bout(monkeypatch, link='air', tail_done=True)
    bout.n._held_goal = bout.goal
    offer = bout.tick()
    assert offer is not None and offer.draft.run.link == 'middle'                  # the Task 183 middle landing, its route scanned
    bout = Bout(monkeypatch, link='air', tail_done=True, danger=((25., 0., 34.5, 30.),))   # the gap's air all dangerous
    bout.n._held_goal = bout.goal
    offer = bout.tick()
    held = bout.notes('transfer_follow_held')
    assert held and not bout.notes('transfer_follow_seam') and offer is not None
    assert offer.mask & B['R'] and not offer.mask & B['L'] and offer.draft.run.v["no_strike"] is True


def test_a_rune_end_entry_binds_past_a_spent_bounce_goal_on_the_same_pair():
    # C18 sy18_23x 136227: the small rune's caster is the nearer one, the 2.3 target; a spent bounce goal on it was still kept: it is no
    # binding of this rune end's entry (only a SWITCH goal of the same RUNE_END frame is)
    from ssbot.combat.knife_chain_commitment import MoveInstance
    from ssbot.combat.knife_chain_transfer import TransferGoal
    from tests.test_knife_chain_transfer import cast_scene
    from tests.test_seq312_384 import _prefs, _rune_end_entry
    from tests.test_target_entry_attack import native
    n, s = native(), cast_scene()
    s["ents"][0]["fsms"][0].update(state="Idle", t=.05)
    n._transfer_goal = TransferGoal(8, 8, 900, 15., "BOUNCE", MoveInstance(8, 880, "CC_SLAM"))
    entry = _rune_end_entry(target=8, source=8)
    n.goal_preferences(s, _prefs(entry), handoff=True)
    g = n._transfer_goal
    assert g.source_kind == "SWITCH" and g.responsibility == MoveInstance(8, 990, "RUNE_END")
    n.goal_preferences(s, _prefs(entry), handoff=True)
    assert n._transfer_goal is g                                                 # bound once: the same rune end is not bound again


def test_the_strike_bound_hands_back_past_its_bound_only_for_the_outside_kind():
    from ssbot.combat import knife_chain_air_native as AN
    cls = next(c for c in vars(AN).values() if isinstance(c, type) and "_strike_bound" in vars(c))
    me = NS(_transfer_goal=T.TransferGoal(8, 7, 990, 1., "SWITCH", NS(family="CC_SLAM")))
    prefs = NS(strike_bound=(8, 26.1, 27., -1, 1052, 16, "outside"))
    assert cls._strike_bound(me, 1000, prefs, 8) == (26.1, 27., -1, 1052, 16, "outside")
    prefs = NS(strike_bound=(8, 21.5, 20., 1, 1072, None, "seam"))
    assert cls._strike_bound(me, 1000, prefs, 8) == (21.5, 20., 1, 1072, None, "seam")
    assert cls._strike_bound(me, 1000, prefs, 7) is None                          # another target
    me.__dict__["_transfer_goal"] = T.TransferGoal(8, 8, 990, 1., "BOUNCE", NS(family="CC_SLAM"))
    assert cls._strike_bound(me, 1000, prefs, 8) is None                          # never its bounce
