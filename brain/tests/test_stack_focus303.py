"""Task 182 seq 303 (the person: two Clappers stacked, passing through each other: the near one must become the focus), through the real L2 entry."""
from dataclasses import replace

import pytest

from ssbot.combat.tactics import clapper_scene as S, gauntlet as G
from tests.test_clapper_priority import change, manual, scene, step  # noqa: F401  (manual: the autouse switches)


def goal_on(tac, iid, x):
    tac.goal = G.Goal(G.RUSH, iid, x + 4., 1., family=G.CC_IDLE)


@pytest.mark.parametrize("xs,hx", [((20., 23.), 27.), ((27., 24.), 20.)], ids=["she right of the stack", "she left of it"])
@pytest.mark.parametrize("listed_last", [False, True], ids=["near one listed last", "near one listed first"])
def test_the_near_one_of_a_stack_becomes_the_focus(xs, hx, listed_last):
    tac, ws, fc = scene(xs=xs, hx=hx)
    if listed_last:
        fc.subjects = list(reversed(fc.subjects))
    out = step(tac, ws, fc)
    assert out.target == 8 and tac.goal.target == 8
    assert tac.last["clapper_winner"]["rule"] == "keep" and tac.last["clapper_winner"]["target"] == 8
    assert out.hit_w[8] > out.hit_w[7] and out.boss_x == xs[1]        # the action layer's inputs follow, not only the log


def test_the_switch_is_taken_at_once_not_at_the_next_period():
    tac, ws, fc = scene(xs=(20., 30.), hx=34.)
    out = step(tac, ws, fc)
    assert out.target == 7
    change(fc, 8, pos=(24., 7.45))
    while (tac.n + 1) % tac.rules.period == 0:
        step(tac, ws, fc)
    out = step(tac, ws, fc)
    assert out.target == 8 and "keep focus asked" in tac.last["clapper_eval"]["triggers"]


def test_once_switched_it_stays_and_does_not_flip_back():
    tac, ws, fc = scene(xs=(20., 23.), hx=27.)
    targets = [step(tac, ws, fc).target for _ in range(20)]
    assert set(targets) == {8}


@pytest.mark.parametrize("wobble", [0., .1, -.1, .25, -.25])
def test_near_equal_distances_keep_the_focus_without_jitter(wobble):
    tac, ws, fc = scene(xs=(20., 22.), hx=21.2 + wobble)            # 1.2 and .8 u (and the wobble): inside the margin
    assert all(step(tac, ws, fc).target == 7 for _ in range(14))


def test_exactly_on_the_margin_is_not_clearly_nearer():
    tac, ws, fc = scene(xs=(20., 23.), hx=22.)                       # 2.0 and 1.0 u: exactly NEARER_U
    assert step(tac, ws, fc).target == 7


def test_a_pair_apart_keeps_the_focus():
    tac, ws, fc = scene(xs=(20., 24.6), hx=30.)                      # roots 4.6 u apart: the bodies do not touch
    assert step(tac, ws, fc).target == 7


def test_just_inside_the_stack_distance_switches():
    tac, ws, fc = scene(xs=(20., 24.4), hx=30.)
    assert step(tac, ws, fc).target == 8


@pytest.mark.parametrize("state", ["Air", "Jump"])
def test_the_near_one_in_flight_is_no_target(state):
    tac, ws, fc = scene(xs=(20., 23.), hx=27.)
    change(fc, 8, family=G.CC_JUMP, state=state)
    assert S.stacked_nearer(type("Sc", (), dict(keep=fc.subjects[0], subjects=fc.subjects, hx=27.))) is None


@pytest.mark.parametrize("state", sorted(S.SLAMMING))
def test_a_slamming_focus_is_not_left(state):
    tac, ws, fc = scene(xs=(20., 23.), hx=27.)
    change(fc, 7, family=G.CC_SLAM, state=state, committed=True)
    assert S.stacked_nearer(type("Sc", (), dict(keep=fc.subjects[0], subjects=fc.subjects, hx=27.))) is None


def test_a_casting_focus_behind_the_near_one_gives_way():
    # the recorded shape (live bout 23, 23414): the focus casts behind the near one, which stands idle next to her
    tac, ws, fc = scene(xs=(20., 23.), hx=27.)
    change(fc, 7, family=G.CC_CAST, state="Spell Antic", committed=True)
    assert step(tac, ws, fc).target == 8


@pytest.mark.parametrize("xs,hx", [((20., 20.), 27.), ((20., 40.), 30.)], ids=["same root, she outside", "same room and distance, she between"])
def test_no_focus_on_an_exact_tie_does_not_read_the_entity_order(xs, hx):
    picks = set()
    for order in (False, True):
        tac, ws, fc = scene(xs=xs, hx=hx)
        tac.goal = None
        if order:
            fc.subjects = list(reversed(fc.subjects))
        picks.add(step(tac, ws, fc).target)
    assert picks == {7}


def test_no_focus_in_the_middle_after_entering_it_does_not_read_the_entity_order():
    picks = set()
    for order in (False, True):
        tac, ws, fc = scene(xs=(20., 40.), hx=30.)
        if order:
            fc.subjects = list(reversed(fc.subjects))
        step(tac, ws, fc)                    # the entry into the middle (its own rule)
        tac.goal = None
        picks.add(step(tac, ws, fc).target)
    assert picks == {7}


def test_a_far_cast_in_the_stack_does_not_steal_the_near_focus():
    tac, ws, fc = scene(xs=(20., 23.), hx=27.)
    goal_on(tac, 8, 23.)
    step(tac, ws, fc)
    change(fc, 7, family=G.CC_CAST, state="Spell Antic", committed=True)
    assert step(tac, ws, fc).target == 8
    assert "near" not in {c["rule"] for c in tac.last["clapper_choices"]}


def test_a_far_slam_in_the_stack_still_takes_the_focus_and_keeps_it():
    tac, ws, fc = scene(xs=(20., 23.), hx=27.)
    goal_on(tac, 8, 23.)
    step(tac, ws, fc)
    change(fc, 7, family=G.CC_SLAM, state="Slam Antic", committed=True)
    assert step(tac, ws, fc).target == 7 and tac.last["clapper_winner"]["rule"] == "near"
    assert all(step(tac, ws, fc).target == 7 for _ in range(8))          # no hand-back to the near one while it slams


def test_a_near_one_in_its_own_near_antic_is_taken_by_the_stack_rule_as_before_by_near_threat():
    tac, ws, fc = scene(xs=(20., 23.), hx=27.)
    change(fc, 8, family=G.CC_SLAM, state="Slam Antic", committed=True)
    assert step(tac, ws, fc).target == 8


def test_a_new_pick_entry_on_a_switch_uses_the_shared_entry():
    tac, ws, fc = scene(xs=(20., 23.), hx=27.)
    step(tac, ws, fc)
    tac2, ws2, fc2 = scene(xs=(20., 23.), hx=27.)
    change(fc2, 7, family=G.CC_CAST, state="Cast 1", committed=True)
    out = step(tac2, ws2, fc2)
    assert out.target == 8 and (out.entry_attack is None or out.entry_attack.target == 8)
