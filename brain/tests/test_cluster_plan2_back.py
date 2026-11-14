"""The person 11-13 (quote 125, rx411 bout 2 2:03): the cluster plan's attack variant (plan 2: slash in the aim, retreat on the take-off,
come back and slash on) has no way into the middle.

Live 9330-9496: the plan was made on 582496's jump cast, with 582490 idle as the other; 582490 jumped too while she retreated (9390-9472).
At 9486 the hazards were over and the way back went to 582490, standing nearer in its Slam Recover; that phase's other_move test took its
jump family for a new move and invalidated the plan, and the middle return, due since 582496's move ended near her, took the scene and
sent her up into the seam. Now the other one's jump already past its hazards by the plan's own jumper rule is no new move for the way
back, and the moves plan 2 came back from make no public middle return (sc.mem["back_skip"], read by clapper_tactics.middle_return)."""
import pytest

from ssbot.combat.tactics import clapper_plans as CP, gauntlet as G
from tests.test_clapper_priority import change, manual, scene, seq312_off, step   # noqa: F401  (autouse manual-B fixture)
from tests.test_l2_plan182 import antic, go_, planned
from tests.test_middle_return313 import near_attack


def test_a_skipped_move_makes_no_middle_return_a_later_one_does():
    tac, ws, fc = scene(xs=(20., 34.), hx=15.); step(tac, ws, fc)
    tac._clapper_priority["back_skip"] = {7: ws.stamp.t_game_s + 10.}      # begun before the limit
    near_attack(tac, ws, fc)
    assert tac.last["clapper_back"] is None and tac.last["clapper_winner"]["rule"] != "back"
    assert tac._clapper_priority.get("back") is None and tac._clapper_priority["back_skipped"]["iid"] == 7
    tac._clapper_priority["back_skip"] = {7: ws.stamp.t_game_s - 1.}       # a move begun after the limit: the return as before
    out = near_attack(tac, ws, fc)
    assert tac.last["clapper_winner"]["rule"] == "back" and tac.last["clapper_back"]["move"] == [7, G.CC_SLAM] and out.target == 8


def _cluster(monkeypatch):
    tac, ws, fc = planned(monkeypatch, xs=(36., 37.), hx=28.)
    go_(tac, ws, fc)
    antic(tac, ws, fc)
    go_(tac, ws, fc); go_(tac, ws, fc)
    ex = tac.plan_runner.exec
    assert ex.plan is not None and ex.plan.scene == "cluster" and ex.plan.instance[0] == 7 and ex.plan.get("other") == 8
    return tac, ws, fc, ex


@pytest.mark.parametrize("branch", ["attack", "lure"])
def test_plan_2_marks_its_jumpers_move_for_no_middle_return(monkeypatch, branch):
    tac, ws, fc, ex = _cluster(monkeypatch)
    made = ex.plan.made_t
    ex.select(branch, ws.stamp.t_game_s)
    go_(tac, ws, fc)
    skip = tac._clapper_priority.get("back_skip") or {}
    assert (skip.get(7) == pytest.approx(made)) if branch == "attack" else 7 not in skip


@pytest.mark.parametrize("branch,before,dropped", [("attack", True, True), ("attack", False, False), ("lure", True, False)])
def test_plan_2_drops_a_middle_return_pending_from_before_it(monkeypatch, branch, before, dropped):
    # replay x4_ep1 9498: a return due since 582490's earlier jump (before the plan), held while the plan ran, took the scene the tick plan 2
    # was done; a return from a move begun after the plan was made, or under the lure, stays as before
    tac, ws, fc, ex = _cluster(monkeypatch)
    made = ex.plan.made_t
    start = made - 1. if before else made + 1e-3
    due = dict(family=G.CC_JUMP, start_t=start, near=True, iid=8, end_t=start + .5, end_hx=28., end_state="Idle", offered=False)
    tac._clapper_priority["back"] = due
    ex.select(branch, ws.stamp.t_game_s)
    go_(tac, ws, fc)
    if dropped:
        assert tac._clapper_priority.get("back") is None
        assert tac._clapper_priority["back_skipped"]["iid"] == 8 and tac._clapper_priority["back_skipped"]["start_t"] == start
    else:
        assert tac._clapper_priority.get("back") is due


@pytest.mark.parametrize("family,state,over", [(G.CC_JUMP, "Slam Recover", True), (G.CC_JUMP, "Air", False),
                                               (G.CC_JUMP_CAST, "Slam Recover", False)])
def test_the_other_ones_own_jump_on_the_way_back(monkeypatch, family, state, over):
    # over: landed and in its Slam Recover (live 9486), the way back to it goes on and its move makes no middle return; still in the air,
    # or a jump cast whose rune has not burst yet (RUNE_OVER_S after the landing): a new move, the plan ends as before
    tac, ws, fc, ex = _cluster(monkeypatch)
    ex.select("attack", ws.stamp.t_game_s)
    ex.name = "attack_back_other"
    change(fc, 8, family=family, state=state, committed=True)
    ws.entities[1].fsm = [("Control", state, .02)]
    go_(tac, ws, fc)
    if over:
        assert ex.plan is not None and ex.name == "attack_back_other"
        assert tac._clapper_priority["back_skip"][8] == pytest.approx(ws.stamp.t_game_s)
    else:
        assert ex.plan is None and ex.status == "invalid" and ex.reason == "other_move"
        assert 8 not in (tac._clapper_priority.get("back_skip") or {})


def test_the_way_back_reaching_its_body_hands_it_to_idlehit_for_that_tick(monkeypatch):
    # the plan's in_reach end of a way-back phase names its body (PlanRunner.arrived, the policy's two_play.plan_entry) for one tick
    from ssbot.core.worldstate import E
    tac, ws, fc, ex = _cluster(monkeypatch)
    ex.select("attack", ws.stamp.t_game_s)
    ex.name = "attack_back_jumper"                                           # target 7 (at 36), landed: in its Slam Recover
    change(fc, 7, state="Slam Recover")
    ws.entities[0].fsm = [("Control", "Slam Recover", .02)]
    y = float(ws.hero.pos.v[1])
    ws.hero.pos = E((33., y), conf=1.)                                       # within edge_u 2.7 of its body
    ws.hero.hurtbox = [(32.75, y - 1.6), (33.25, y - 1.6), (33.25, y + .4), (32.75, y + .4)]
    go_(tac, ws, fc)
    r = tac.plan_runner
    assert ex.plan is None and ex.status == "complete" and ex.reason == "in_reach" and r.arrived == 7
    go_(tac, ws, fc)
    assert r.arrived is None


# ---- two_play: plan 2's arrival starts IdleHit's side slash (rx411 2:03 replay: the press came only because she was inside the
# 30-frame window of 582490's own Idle entry; a longer way back meets no window and the planner hops about) ----

def _on_two(monkeypatch):
    from ssbot.combat import two_play as tp
    for k in ("CHASE", "IDLEHIT", "CAST", "SPACE", "OPEN", "ANY"):
        monkeypatch.setattr(tp, k, True)
    return tp


def _run_entry(two, ss, entry_f=(), focus=7):
    from ssbot.combat import slam_play as sp
    out = []
    for s in ss:
        two.observe(s["f"], s, s["f"] / 60.0)
        if s["f"] in entry_f:
            two.plan_entry = frozenset((focus,))                              # (the policy, after observe and before step)
        out.append(two.step(s["f"], s, sp.on_ground(s), True, focus, s["f"] / 60.0))
    return out


@pytest.mark.parametrize("state", ["Idle", "Slam Recover", "Walk"])
def test_plan_2_arrival_starts_the_side_slash_without_the_bodys_own_entry(monkeypatch, state):
    from ssbot.combat import slam_play as sp
    from tests.test_sp9 import two_state
    tp = _on_two(monkeypatch)
    two = tp.TwoPlay()
    two.prev[7] = (state, .4)                                                # long in that state: no entry edge, its window over
    assert _run_entry(two, [two_state(1000, state, .5)]) == [None]          # nothing starts by itself
    out = _run_entry(two, [two_state(1001, state, .52), two_state(1002, state, .54)], entry_f={1001})
    if state == "Walk":
        assert out == [None, None] and two.stats().get("idle_runs", 0) == 0  # IdleHit's bodies only (Idle, Slam Recover)
    else:
        assert out == [sp.M_A | sp.M_R, sp.M_A | sp.M_R] and two.stats()["idle_press"] == 1   # the press and its second frame


def test_plan_2_arrival_restarts_a_run_already_spent_and_keeps_its_guards(monkeypatch):
    from ssbot.combat import slam_play as sp
    from tests.test_sp9 import two_state
    tp = _on_two(monkeypatch)
    two = tp.TwoPlay()
    out = _run_entry(two, [two_state(1000, "Slam Recover", .3), two_state(1001, "Idle", 0.), two_state(1002, "Idle", 1 / 60),
                           two_state(1003, "Idle", 2 / 60)])
    assert out[1] == sp.M_A | sp.M_R and out[3] is None                      # its own entry's press, then the run is spent
    out = _run_entry(two, [two_state(1004, "Idle", 3 / 60), two_state(1005, "Idle", 4 / 60)], entry_f={1004})
    assert out == [sp.M_A | sp.M_R, sp.M_A | sp.M_R] and two.stats()["idle_press"] == 2
    two = tp.TwoPlay()
    two.prev[7] = ("Idle", .4)
    busy = two_state(1001, "Idle", .52, b_st="Slam Antic", b_x=36.)          # the other one's hammer can reach her: no press
    assert _run_entry(two, [two_state(1000, "Idle", .5), busy], entry_f={1001}) == [None, None]


def test_without_the_rule_the_way_back_to_the_landed_other_one_is_invalidated(monkeypatch):
    # the rx411 2:03 behaviour itself (the rule masked): its jump family read as a new move
    monkeypatch.setattr(CP.PlanRunner, "_other_jump_over", lambda self, sc, o, dry=False: False)
    tac, ws, fc, ex = _cluster(monkeypatch)
    ex.select("attack", ws.stamp.t_game_s)
    ex.name = "attack_back_other"
    change(fc, 8, family=G.CC_JUMP, state="Slam Recover", committed=True)
    ws.entities[1].fsm = [("Control", "Slam Recover", .02)]
    go_(tac, ws, fc)
    assert ex.plan is None and ex.reason == "other_move"
