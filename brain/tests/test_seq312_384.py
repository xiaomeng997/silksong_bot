"""Task 182 seq 312 #384 (Sol REVIEW383): IdleHit yields before it prepares (A), plan 3.4 in the middle scene (B), 2.2's strike place covered by
the small rune's bombs (X14), and the package's executors: the stomp entry of 1.2.1 / 1.2.2 / the way into the middle (F's slam its source)
and 2.3's one closing stomp entry bound to the rune's end."""
from types import SimpleNamespace as NS

import numpy as np
import pytest

from ssbot.combat.tactics import clapper_plans as CP, clapper_separated as SEP, gauntlet as G
from ssbot.combat.tactics.modes import EntryAttack
from tests.test_clapper_priority import change, manual, scene, step   # noqa: F401  (autouse manual-B fixture)
from tests.test_separated312 import cast, end_rune, hero_at, slam, start, tick


@pytest.fixture(autouse=True)
def plans_on(monkeypatch):
    monkeypatch.setattr(CP, "ENABLED", True)


# ---- A: IdleHit yields before it prepares anything ----

def _run(two, ss, yield_f=(), focus=7):
    from tests.test_sp9 import sp
    out = []
    for s in ss:
        two.observe(s["f"], s, s["f"] / 60.0)
        if s["f"] in yield_f:
            two.idle_yield = True
        out.append(two.step(s["f"], s, sp.on_ground(s), True, focus, s["f"] / 60.0))
    return out


@pytest.fixture
def idle_only(monkeypatch):
    from ssbot.combat import two_play as TP
    monkeypatch.setattr(TP, "IDLEHIT", True)
    for k in ("ASW", "ESC", "JUMPHIT", "WALKOUT", "OPEN"):
        monkeypatch.setattr(TP, k, False)
    return TP


def test_idlehit_under_l2_prepares_nothing_and_its_run_goes_on_after(idle_only):
    from tests.test_sp9 import sp, two_state
    two = idle_only.TwoPlay()
    out = _run(two, [two_state(1000, "Slam Recover", .3), two_state(1001, "Idle", 0.), two_state(1002, "Idle", 1 / 60)],
               yield_f={1001, 1002})
    assert out[1:] == [None, None]
    assert two.idle is not None and two.idle.k_press is None and two._press_f is None and two.idle.sent == []
    assert two.stats()["idle_press"] == 0                       # the keys never sent are no press
    out = _run(two, [two_state(1003, "Idle", 2 / 60), two_state(1004, "Idle", 3 / 60)])
    assert out == [sp.M_A | sp.M_R, sp.M_A | sp.M_R]            # L2 let go: the same run presses by its own rules
    assert two.idle.k_press == 2 and two.stats()["idle_press"] == 1


def test_a_press_already_sent_still_sends_its_second_frame_under_l2(idle_only):
    from tests.test_sp9 import sp, two_state
    two = idle_only.TwoPlay()
    out = _run(two, [two_state(1000, "Slam Recover", .3), two_state(1001, "Idle", 0.), two_state(1002, "Idle", 1 / 60)],
               yield_f={1002})
    assert out[1] == sp.M_A | sp.M_R and out[2] == sp.M_A | sp.M_R and two.stats()["idle_press"] == 1


# ---- B: plan 3.4 in the middle scene ----

def test_a_jumper_behind_a_live_circle_from_the_middle_takes_no_route_across_it():
    # Sol REVIEW383 B: she 25 between 8 (20) and the jumper 7 (40), a live circle 27..35 between her and the jumper
    from dataclasses import replace
    from tests.test_l2_plan182 import body, plan_of, request
    J = body(7, 40., "Jump Antic", "CC_JUMP", facing=-1)
    W = body(8, 20.)
    q = request("middle", J, W, hx=25.)
    open_ = plan_of(q)
    q3 = replace(q, rune_across=True, circles=((27., 35.),))
    plan = plan_of(q3)
    for name in ("stay", "under", "over"):
        c, c0 = plan.candidate(name), open_.candidate(name)
        spots = [c0.get(k) for k in ("aim_x", "end_x") if c0.get(k) is not None]
        across = any(CP.rune_cut(((27., 35.),), q.hand.x, float(x), q.left, q.right, q.pad) != float(x) for x in spots)
        if c0.feasible and across:
            assert not c.feasible and "3.4" in c.reason, name
        elif c0.feasible:
            assert c.feasible, name                               # a place on the walker's side keeps its option
    assert plan.get("rune_across") is True


def test_the_middle_layout_with_the_circle_between_her_and_the_jumper_is_a_rune_jumper():
    from ssbot.combat.tactics.clapper_scene import geometry
    tac, ws, fc = start((20., 40.), 25.)                  # N 7 at 20, the jumper F 8 at 40
    change(fc, 8, family=G.CC_JUMP, state='Jump Antic', committed=True)
    tick(tac, ws, fc)
    geo = geometry(tac, ws, list(fc.subjects))
    j = next(s for s in fc.subjects if s.iid == 8)
    assert CP.rune_jumper(j, geo, 25., ((27., 35.),))      # the circle is across her way to the jumper ...
    assert CP.parent_scene(list(fc.subjects), geo, 25., ((27., 35.),))[:2] == ("middle", j)   # ... and the parent stays the middle


def test_the_middle_request_through_l2_carries_the_live_circle_and_its_plan_gates_the_routes_across(monkeypatch):
    # the same layout through the real L2 entry and the inline plan channel: the request names the circle, the plan runs gated
    from tests.test_l2_plan182 import antic, go_, planned
    tac, ws, fc = planned(monkeypatch, xs=(20., 40.), hx=25.)
    tac.rune_life = NS(live=lambda t: [NS(lo=27., hi=35.)])
    r = tac.plan_runner
    seen = []
    orig = r.channel.request
    r.channel.request = lambda key, q: (seen.append(q), orig(key, q))[1]
    antic(tac, ws, fc, iid=8)
    for _ in range(3):
        go_(tac, ws, fc)
    q = next(q for q in seen if q.scene == "middle")
    assert q.rune_across is True and q.circles == ((27., 35.),) and q.jumper.iid == 8
    tac.rune_life = NS(live=lambda t: [])                 # without the circle the same request names none
    seen.clear()
    r.exec.end("invalid", "test", ws.stamp.t_game_s)
    go_(tac, ws, fc)
    assert all(not q.rune_across and q.circles == () for q in seen if q.scene == "middle")


# ---- X14: 2.2's strike place covered by the small rune's bombs ----

def _bombs(*rows):
    return np.asarray(rows, float)


def test_a_strike_place_covered_on_a_frame_of_its_window_is_no_strike(monkeypatch):
    tac, ws, fc = start((20., 30.), 15.)
    cast(tac, ws, fc, 7)
    sc = NS(geo=None, tac=tac, hx=15.)
    from ssbot.combat.tactics.clapper_scene import geometry
    sc.geo = geometry(tac, ws, list(fc.subjects))
    s7 = next(s for s in fc.subjects if s.iid == 7)
    top = sc.geo["tops"][7]
    y = top + SEP.STRIKE_DY + .133                                # the bomb centred on her box at the contact height
    r = tac.rules
    k0 = int(np.ceil((r.start_s + 5. / r.run_u_s) * 60.))       # she can be there (5 u from 15) from this frame
    assert SEP.strike_covered(sc, s7, 20., _bombs((7, 20., y, 2., 0, 400)))                  # lit through the window
    assert SEP.strike_covered(sc, s7, 20., _bombs((7, 20., y, 2., k0 + 3, k0 + 5)))          # lit on three of its frames
    assert not SEP.strike_covered(sc, s7, 20., _bombs((7, 20., y, 2., 0, k0 - 1)))           # out before she gets there
    assert not SEP.strike_covered(sc, s7, 20., _bombs((7, 20., y, 2., k0 + SEP.STRIKE_F + 1, 400)))   # lit after the window
    assert not SEP.strike_covered(sc, s7, 20., _bombs((7, 20., 2.0, 1.5, 0, 400)))           # a ground bomb below the strike
    assert not SEP.strike_covered(sc, s7, 20., None)


def test_small_rune_targets_skip_a_covered_strike_and_hand_on_when_none_is_left(monkeypatch):
    tac, ws, fc = start((20., 30.), 25.)                    # she between the two: both reachable, the caster 7
    cast(tac, ws, fc, 7)
    assert tac.last["clapper_rune_down"]["case"] == "2.2 caster"
    covered = {7}
    monkeypatch.setattr(SEP, "strike_covered", lambda sc, s, x, bombs: s.iid in covered)
    out = tick(tac, ws, fc)
    assert tac.last["clapper_rune_down"]["case"] == "2.2 other" and out.target == 8
    covered.add(8)
    tick(tac, ws, fc)                                       # the pick this asks: no intent over the bombs, another rule takes it
    assert tac.last["clapper_rune_down"]["case"] == "2.2 none strikable"
    assert (tac.last.get("clapper_winner") or {}).get("rule") != "rune_down"
    tick(tac, ws, fc)
    assert (tac.last.get("clapper_winner") or {}).get("rule") != "rune_down"


# ---- the executors: stomp entries ----

def test_n_reaching_past_the_edge_gets_the_stomp_entry_on_n_with_fs_slam_its_source():
    tac, ws, fc = start((20., 33.), 40.)                  # 1.2.2 (tests/test_separated312's layout)
    out = slam(tac, ws, fc)
    e = out.entry_attack
    assert tac.last["clapper_sep_slam"]["branch"] == "1.2.2"
    assert isinstance(e, EntryAttack) and (e.target, e.kind, e.source, e.source_family) == (8, "stomp", 7, "CC_SLAM")
    again = tick(tac, ws, fc)
    assert again.entry_attack is e                        # one entry for the whole slam: the chain never re-binds it


def _down_hit(ws, iid):
    from ssbot.core.worldstate import Ev
    ws.events = [NS(kind=Ev.HIT_DEALT, data=NS(target_id=iid, attack="Nail", src="DownSlash"))]


def test_the_1_2_2_down_slash_holds_its_bounce_off_the_middle_and_1_2_1_does_not():
    tac, ws, fc = start((20., 33.), 40.)                  # 1.2.2
    assert slam(tac, ws, fc).hold_over == frozenset({8})
    tac, ws, fc = start((20., 36.), 45.)                  # 1.2.1: the room past N is itself out of the range
    assert slam(tac, ws, fc).hold_over == frozenset()
    tac, ws, fc = start((20., 30.), 40.)                  # 1.2.3
    assert slam(tac, ws, fc).hold_over == frozenset()


def test_n_struck_in_the_slam_takes_no_second_entry_and_down_after_both_hammers_no_way_over_it():
    from ssbot.core.worldstate import E
    tac, ws, fc = start((20., 33.), 40.)                  # 1.2.2
    ws.hero.contact = E("GROUND")
    out = slam(tac, ws, fc)
    assert out.entry_attack is not None
    _down_hit(ws, 8)
    out = tick(tac, ws, fc)                               # the down slash's real contact on 8 completes its entry
    ws.events = []
    assert out.entry_attack is None
    change(fc, 7, state="Slam 0")
    out = tick(tac, ws, fc)                               # a pick (the slammer's state changed): no second entry on the struck one
    assert tac.last["clapper_winner"]["rule"] == "sep_slam" and out.entry_attack is None and out.hold_over == frozenset({8})
    change(fc, 7, state="Slam 2"); tick(tac, ws, fc)
    change(fc, 7, state="Slam Recover"); tick(tac, ws, fc)
    tick(tac, ws, fc)                                     # both hammer stages over, she is down: no way over the struck one, said so
    assert tac.last["clapper_sep_slam"] is None
    assert any("struck in this slam" in n["what"] for n in tac.last.get("clapper_sep_notes") or [])


def test_n_struck_while_she_is_still_up_after_both_hammers_leaves_the_middle_to_the_chains_own_follow_up():
    from ssbot.core.worldstate import E
    tac, ws, fc = start((20., 33.), 40.)
    slam(tac, ws, fc)
    _down_hit(ws, 8)
    tick(tac, ws, fc)
    ws.events = []
    ws.hero.contact = E("AIR")                            # up from the bounce
    change(fc, 7, state="Slam 2"); tick(tac, ws, fc)
    change(fc, 7, state="Slam Recover"); tick(tac, ws, fc)
    out = tick(tac, ws, fc)
    assert tac.last["clapper_sep_slam"] is None and out.entry_attack is None and out.hold_over == frozenset()
    note = next(n for n in tac.last.get("clapper_sep_notes") or [] if "struck in this slam" in n["what"])
    assert note["grounded"] is False                      # no stage of this unit: the bounce's follow-up, if it still runs, is the chain's


def test_the_slam_edge_side_slash_and_the_way_out_take_no_stomp_entry():
    tac, ws, fc = start((20., 30.), 40.)                  # 1.2.3
    out = slam(tac, ws, fc)
    assert tac.last["clapper_sep_slam"]["branch"] == "1.2.3" and out.entry_attack is None


def test_past_n_on_its_inner_side_the_entry_ends_and_its_side_slash_counts():
    tac, ws, fc = start((20., 36.), 45.)                  # 1.2.1: room past N outside the range
    out = slam(tac, ws, fc)
    assert tac.last["clapper_sep_slam"]["branch"] == "1.2.1" and out.entry_attack is not None
    hero_at(ws, 34.5)                                     # over it and down on its inner side
    out = tick(tac, ws, fc)
    assert out.entry_attack is None and out.hit_kw[8][0] > 0 and out.hit_kw[8][3] == 0.


def test_the_small_runes_close_at_most_2_5_u_is_one_stomp_entry_bound_to_the_rune_end():
    tac, ws, fc = start((20., 23.), 15.)
    cast(tac, ws, fc, 7)
    out = end_rune(tac, ws, fc, 7)
    a = tac.last["clapper_rune_after"]
    e = out.entry_attack
    assert a["tier"] == "seam" and isinstance(e, EntryAttack)
    assert (e.kind, e.scope, e.event_f, e.source, e.target) == ("stomp", "rune_end", a["f0"], 7, out.target)
    again = tick(tac, ws, fc)
    assert again.entry_attack == e                        # deduplicated: the same rune end, the same entry


def test_the_closing_strikes_entry_ends_with_its_scene():
    from tests.test_separated312 import hit_on
    tac, ws, fc = start((20., 23.), 15.)
    cast(tac, ws, fc, 7)
    out = end_rune(tac, ws, fc, 7)
    assert getattr(out.entry_attack, "scope", None) == "rune_end"
    hit_on(ws, out.target)                                # a side slash hit ends the 2.3 scene (no stomp contact: the entry is not completed)
    out = tick(tac, ws, fc)
    assert tac.last["clapper_rune_after"] is None and out.entry_attack is None and tac.goal.entry_attack is None


def test_the_separated_slams_entry_ends_with_its_scene():
    from ssbot.core.worldstate import E
    tac, ws, fc = start((20., 33.), 40.)                  # 1.2.2
    ws.hero.contact = E("GROUND")
    out = slam(tac, ws, fc)
    assert getattr(out.entry_attack, "scope", None) == "sep_slam"
    change(fc, 7, state="Slam 2"); tick(tac, ws, fc)
    change(fc, 7, state="Slam Recover"); tick(tac, ws, fc)
    out = tick(tac, ws, fc)                               # both hammer stages over: the way into the middle keeps the entry
    assert tac.last["clapper_sep_slam"]["phase"] == "post" and getattr(out.entry_attack, "scope", None) == "sep_slam"
    change(fc, 8, family=G.CC_JUMP, state="Jump Antic", committed=True)   # a new antic ends it
    out = tick(tac, ws, fc)
    assert tac.last["clapper_sep_slam"] is None and getattr(out.entry_attack, "scope", None) != "sep_slam"
    assert getattr(tac.goal.entry_attack, "scope", None) != "sep_slam"


def test_a_package_stomp_entry_is_only_for_a_target_a_strike_witness_reads():
    # 2.3: the closing strike's target evading is no entry (no strike now, only a way into its path); one already given ends with it
    tac, ws, fc = start((20., 23.), 15.)
    cast(tac, ws, fc, 7)
    out = end_rune(tac, ws, fc, 7)
    tgt = out.target
    assert getattr(out.entry_attack, "scope", None) == "rune_end"
    change(fc, tgt, state="Evade Scuttle")
    out = tick(tac, ws, fc)
    assert getattr(out.entry_attack, "scope", None) != "rune_end" and getattr(tac.goal.entry_attack, "scope", None) != "rune_end"
    # 1.2.2: N evading at the slam's start: no stomp entry on it
    tac, ws, fc = start((20., 33.), 40.)
    change(fc, 8, state="Evade Scuttle")
    out = slam(tac, ws, fc)
    assert tac.last["clapper_sep_slam"]["branch"] == "1.2.2" and getattr(out.entry_attack, "scope", None) != "sep_slam"


def test_an_unpressed_scene_stomp_hands_back_when_its_scene_entry_ends(monkeypatch):
    from ssbot.combat import knife_chain_air_native as mod
    from ssbot.combat.knife_chain_commitment import MoveInstance
    from ssbot.combat.knife_chain_transfer import TransferGoal
    from ssbot.knowledge import kinematics as K
    from tests.test_knife_chain_transfer import transfer_motion_scene
    from tests.test_target_entry_attack import native
    r, state, sim = transfer_motion_scene(K.M_NORMAL)    # an active rune_transfer walk Run on 8, nothing pressed
    n = native()
    n.runner, n._clock, n._context = r, .1, (None, sim, None, None)
    entry = _rune_end_entry()
    n._transfer_goal = TransferGoal(8, 7, 995, .1, "SWITCH", MoveInstance(7, 990, "RUNE_END"))
    n._entry_attack_goal = entry
    recovered = []
    monkeypatch.setattr(n, "_recover", lambda why, f: recovered.append(why))
    monkeypatch.setattr(n, "queued_prefix", lambda *a: (int(sim.prefix[0]), "actual fixture prefix"))
    monkeypatch.setattr(mod.B2Geometry, "preflight", lambda self, path: NS(complete=True, contacts=[]))
    fc = NS(rs=NS(trk=NS(T=.1, now={8: (None, None, None), 7: (None, None, NS(fam="CC_IDLE", t0=0.))})))
    n._transfer_offer(state, .1, sim, fc, _prefs(entry, x=46.), True)
    assert not any("ended before its press" in w for w in recovered)                 # its scene still asks for it
    n._transfer_offer(state, .1, sim, fc, _prefs(entry, x=46.).__class__(mode="RUSH", stance_x=46., weights={}, target=8), True)
    assert any("ended before its press" in w for w in recovered)                     # the scene's entry gone: handed back


# ---- the chain: 2.3's entry bound to the rune end (the existing rune_transfer executes it) ----

def _rune_end_entry(event_f=990, target=8, source=7):
    return EntryAttack(target, "stomp", source, "RUNE_END", 2., 10., scope="rune_end", event_f=event_f)


def _prefs(entry, x=38.):
    from ssbot.combat.tactics.modes import GoalPrefs
    return GoalPrefs(mode="RUSH", stance_x=x, weights={}, target=entry.target, entry_attack=entry)


def test_the_chain_binds_one_switch_goal_per_rune_end():
    from dataclasses import replace
    from ssbot.combat.knife_chain_commitment import MoveInstance
    from tests.test_knife_chain_transfer import cast_scene
    from tests.test_target_entry_attack import native
    n, s = native(), cast_scene()
    s["ents"][0]["fsms"][0].update(state="Idle", t=.05)   # the caster back in Idle: the rune is over
    entry = _rune_end_entry()
    n.goal_preferences(s, _prefs(entry), handoff=True)
    g = n._transfer_goal
    assert g.source_kind == "SWITCH" and (g.target, g.caster) == (8, 7) and g.responsibility == MoveInstance(7, 990, "RUNE_END")
    assert g.cast_ta == 20. and n._transfer_ready
    n.goal_preferences(s, _prefs(entry), handoff=True)
    assert n._transfer_goal is g                          # the same rune end: never bound again
    n.goal_preferences(s, _prefs(replace(entry, event_f=1100)), handoff=True)
    assert n._transfer_goal.responsibility == MoveInstance(7, 1100, "RUNE_END")   # the next rune end is its own goal


@pytest.mark.parametrize("blocked", ["clock", "caster", "frame"])
def test_no_rune_end_goal_without_the_clock_the_caster_or_the_rune_end_frame(blocked):
    from tests.test_knife_chain_transfer import cast_scene
    from tests.test_target_entry_attack import native
    n, s = native(), cast_scene()
    s["ents"][0]["fsms"][0].update(state="Idle", t=.05)
    if blocked == "clock":
        n._clock_known = False
    if blocked == "caster":
        s["ents"] = [s["ents"][1]]
    n.goal_preferences(s, _prefs(_rune_end_entry(event_f=None if blocked == "frame" else 990)), handoff=True)
    assert n._transfer_goal is None and not n._transfer_ready


def test_the_rune_end_goal_reaches_the_existing_approach_without_a_tracker_move(monkeypatch):
    # the source confirmation of a SWITCH goal reads the tracker's move of its caster; the rune's end is no move (its caster Idle)
    from ssbot.combat import knife_chain_air_native as mod
    from ssbot.knowledge import kinematics as K
    from tests.test_knife_chain_transfer import transfer_motion_scene
    from tests.test_target_entry_attack import native
    r, state, sim = transfer_motion_scene(K.M_NORMAL)
    r.run = None
    state["ents"][0]["fsms"][0].update(state="Idle", t=.1)
    n = native()
    n._clock = .1
    n.runner = r
    prefs = _prefs(_rune_end_entry(event_f=997), x=48.)
    n.goal_preferences(state, prefs, handoff=True)
    n._context = (None, sim, None, None)
    monkeypatch.setattr(n, "queued_prefix", lambda *a: (int(sim.prefix[0]), "actual fixture prefix"))
    checked = []
    monkeypatch.setattr(mod.B2Geometry, "preflight", lambda self, path: checked.append(path) or NS(complete=True, contacts=[]))
    fc = NS(rs=NS(trk=NS(T=.1, now={8: (None, None, None), 7: (None, None, NS(fam="CC_IDLE", t0=0.))})))
    offer = n._transfer_offer(state, .1, sim, fc, prefs, True)
    assert offer is not None and checked and offer.draft.run.chain == "rune_transfer"
    assert offer.draft.run.v["_entry_source_confirmed"] and not n._receipts and n.commitment is None


def test_a_failed_rune_end_strike_answers_for_the_small_rune_cast_it_followed():
    # the B2 hand-back's failure exposure: the rune end's caster and frame as that small rune's CC_CAST (the only supported reading);
    # its caster already out of the cast states: the 30-frame minimum
    from ssbot.combat.knife_chain_commitment import MoveInstance
    from tests.test_knife_chain_transfer import cast_scene
    from tests.test_target_entry_attack import native
    n, s = native(), cast_scene()
    s["ents"][0]["fsms"][0].update(state="Idle", t=.05)
    run_move = MoveInstance(8, 995, "RUNE_TRANSFER")
    n._transfer_responsibility[run_move] = (MoveInstance(7, 990, "RUNE_END"), 20.)
    x = n._failure_exposure(run_move, 995, 1000, None)
    assert x.move == MoveInstance(7, 990, "CC_CAST")
    x.observe(s, game_time=20.1)
    assert x.observed_end_frame == 1000 and x.through == 1030


# ---- the cross-Clapper hammer the 1.2.2 hold reads ----

def _bounce_goal(caster=8, slammer=7, ta=19.):
    from ssbot.combat.knife_chain_commitment import MoveInstance
    from ssbot.combat.knife_chain_transfer import TransferGoal
    return TransferGoal(caster, caster, 1000, ta, "BOUNCE", MoveInstance(slammer, 940, "CC_SLAM"))


def _slam_scene(state, slam_on=True, body_on=False):
    from tests.test_knife_chain_transfer import cast_scene
    s = cast_scene()
    s["ents"][0]["fsms"][0].update(state=state, t=.1)
    s["ents"][0]["colliders"] = [{"name": "Slam Collider", "enabled": slam_on}, {"name": "Song Heavy Sentry", "enabled": body_on}]
    return s


def test_the_other_ones_slam_is_on_until_its_hammer_collider_is_gone():
    from ssbot.combat import knife_chain_transfer as T
    g = _bounce_goal()
    assert T.cross_hammer_pending(_slam_scene("Slam Antic"), g, 19.1)
    assert T.cross_hammer_pending(_slam_scene("Slam Recover", slam_on=True), g, 21.)
    assert not T.cross_hammer_pending(_slam_scene("Slam Recover", slam_on=False, body_on=True), g, 21.)
    assert T.cross_hammer_pending(_slam_scene("Slam Antic", slam_on=False, body_on=True), g, 19.1)   # this slam's antic: to come
    assert not T.cross_hammer_pending(_slam_scene("Slam Antic", slam_on=False, body_on=True), g, 25.)  # a new slam's antic: not this one


def test_the_cross_hammer_reading_is_only_for_a_bounce_on_the_other_one():
    from dataclasses import replace
    from ssbot.combat import knife_chain_transfer as T
    s = _slam_scene("Slam Antic")
    assert not T.cross_hammer_pending(s, _bounce_goal(caster=7), 19.1)               # the slammer itself: its own tail (bounce_tail)
    assert not T.cross_hammer_pending(s, replace(_bounce_goal(), source_kind="SWITCH"), 19.1)
    assert not T.cross_hammer_pending(s, None, 19.1)
    s["ents"] = [s["ents"][1]]
    assert not T.cross_hammer_pending(s, _bounce_goal(), 19.1)                       # the slammer gone
    assert T.bounce_tail_pending(_slam_scene("Slam Antic"), _bounce_goal(caster=7), 19.1)   # the old reading, unchanged
