"""B2 scope / empirical lower-bound regressions, without a fake world rollout."""
from dataclasses import replace

import pytest

from ssbot.combat.knife_chain_commitment import (
    ContactScan, Continuation, MoveInstance, PathContact, TargetMoveAdmission,
    assess_continuations, check_external_path,
)

MOVE = MoveInstance(12, 100, "CC_SLAM")
BOUNCE = "nominal:12:100:bounce:149"
GUARD = TargetMoveAdmission(MOVE, 100, 149, "h2:test:slam_jump:event100", "pass")


def scan(*contacts, first=100, last=177, path="jump:12:100", complete=True):
    return ContactScan(path, first, last, tuple(contacts), "test geometry fixture", complete)


def check(s, **kw):
    args = dict(path_ref="jump:12:100", target_move=MOVE, first_frame=100, last_frame=177,
                admission=GUARD)
    args.update(kw)
    return check_external_path(s, **args)


def option(name, kind, *, executable=True, admission="pass", contacts=()):
    path = "exit:" + name
    short = scan(*contacts, first=149, last=155, path=path)
    return Continuation(name, kind, BOUNCE, path, 200, executable, admission, short)


def assess(options, full, **kwargs):
    args = dict(target_move=MOVE, bounce_state_ref=BOUNCE, bounce_frame=149,
                short_frames=6, full_scan=full)
    args.update(kwargs)
    return assess_continuations(tuple(options), **args)


def no_full(_):
    pytest.fail("N=2 must not query full exits")


def test_full_77_frame_path_is_accepted_without_ordinary_horizon_limit():
    assert check(scan()).verdict == "pass"


def test_62_frame_support_cannot_certify_a_77_frame_chain():
    r = check(scan(last=162))
    assert (r.verdict, r.reason) == ("unchecked", "path coverage incomplete")


def test_target_current_move_uses_family_admission_only():
    body = PathContact(140, 12, "body", MOVE)
    hammer = PathContact(145, 12, "move", MOVE)
    r = check(scan(body, hammer))
    assert r.verdict == "pass"
    assert r.trusted_target == (body, hammer)


@pytest.mark.parametrize("contact", [
    PathContact(105, 12, "delayed", MOVE),  # own rune during approach (225846 class)
    PathContact(156, 12, "delayed"),       # own small rune, after predicted bounce
    PathContact(154, 99, "move", MoveInstance(99, 101, "CC_SLAM")),
    PathContact(154, 12, "move", MoveInstance(12, 160, "CC_JUMP")),
    PathContact(154, 12, "body"),          # target but not assigned to admitted move
    PathContact(154, None, "other"),
])
def test_no_iid_wide_exemption_or_predicted_pogo_mask(contact):
    r = check(scan(contact))
    assert r.verdict == "reject"
    assert r.retained == (contact,)


def test_preparation_current_frame_is_included():
    contact = PathContact(100, 90, "body")
    assert check(scan(contact)).retained == (contact,)
    assert check(scan(first=101)).verdict == "unchecked"


@pytest.mark.parametrize("s", [None, scan(complete=False), scan(path="other")])
def test_unknown_scan_or_path_is_never_clear(s):
    assert check(s).verdict == "unchecked"


def test_known_collision_rejects_even_an_incomplete_scan():
    assert check(scan(PathContact(105, 99, "body"), last=110, complete=False)).verdict == "reject"


def test_two_directions_enable_explicit_lower_bound_without_full_exits():
    opts = [option("left", "left_landing"), option("right", "right_landing")]
    r = assess(opts, no_full)
    assert (r.verdict, r.mode, r.full_checked) == ("pass", "lower_bound", ())
    assert r.qualifying_kinds == ("left_landing", "right_landing")
    assert "unexamined" in r.reason


def test_close_dash_rows_count_as_one_type_and_are_fully_checked():
    opts = [option(str(i), "dash_out") for i in range(3)]
    calls = []
    def blocked(o):
        calls.append(o.option_id)
        return scan(PathContact(185, 99, "body"), first=149, last=200, path=o.path_ref)
    r = assess(opts, blocked)
    assert (r.verdict, r.mode, r.qualifying_kinds) == ("reject", "none", ("dash_out",))
    assert calls == ["0", "1", "2"]


def test_one_survivor_can_pass_by_full_handback_check():
    opt = option("dash", "dash_out")
    r = assess([opt], lambda o: scan(first=149, last=200, path=o.path_ref))
    assert (r.verdict, r.mode, r.full_checked) == ("pass", "full_exit", ("dash",))


def test_full_exit_cannot_end_at_short_horizon():
    opt = option("dash", "dash_out")
    r = assess([opt], lambda o: o.short_scan)
    assert r.verdict == "unchecked"
    assert r.full_checked == ("dash",)


def test_same_owner_rune_removes_a_short_exit_type():
    opts = [option("left", "left_landing"),
            option("right", "right_landing", contacts=(PathContact(150, 12, "delayed", MOVE),))]
    r = assess(opts, lambda o: scan(first=149, last=200, path=o.path_ref))
    assert r.mode == "full_exit"
    assert r.qualifying_kinds == ("left_landing",)
    blocked = next(c for c in r.checks if c.option_id == "right")
    assert (blocked.stage, blocked.verdict) == ("short", "reject")
    assert blocked.path_result.retained[0].kind == "delayed"


@pytest.mark.parametrize("change", [
    {"first_executable": False}, {"first_executable": None},
    {"admission": "reject"}, {"admission": "unchecked"},
    {"short_scan": None},
])
def test_unencoded_or_unexecutable_repeat_strike_never_counts(change):
    opt = replace(option("repeat", "repeat_downslash"), **change)
    r = assess([opt], no_full)
    assert r.verdict != "pass"
    assert r.qualifying_kinds == ()


def test_no_usable_kind_means_do_not_jump():
    r = assess([], no_full)
    assert (r.verdict, r.mode) == ("reject", "none")
    assert "do not jump" in r.reason


def test_one_known_and_one_unknown_cannot_reach_threshold():
    opts = [option("left", "left_landing"), option("right", "right_landing", executable=None)]
    r = assess(opts, lambda _: None)
    assert (r.verdict, r.qualifying_kinds) == ("unchecked", ("left_landing",))


def test_full_exit_defects_are_not_relabelled_as_low_coverage():
    def defect(_):
        raise RuntimeError("adapter defect")
    with pytest.raises(RuntimeError, match="adapter defect"):
        assess([option("dash", "dash_out")], defect)


@pytest.mark.parametrize("opts,kw,match", [
    ([option("left", "left_landing"), option("left", "right_landing")], {}, "duplicate"),
    ([replace(option("left", "left_landing"), bounce_state_ref="other")], {}, "different bounce"),
    ([], {"minimum_kinds": 0}, "threshold"),
    ([], {"short_frames": 0}, "threshold"),
])
def test_invalid_domains_fail_explicitly(opts, kw, match):
    with pytest.raises(ValueError, match=match):
        assess(opts, no_full, **kw)


def test_short_check_includes_bounce_and_needs_coverage():
    opt = option("left", "left_landing")
    opt = replace(opt, short_scan=scan(first=150, last=155, path=opt.path_ref))
    r = assess([opt, option("right", "right_landing")], lambda _: None)
    assert r.verdict == "unchecked"
    assert r.qualifying_kinds == ("right_landing",)


@pytest.mark.parametrize("kind", ["body", "move"])
def test_prebounce_admission_never_exempts_postbounce_contacts(kind):
    contact = PathContact(150, 12, kind, MOVE)
    r = check(scan(contact))
    assert r.verdict == "reject"
    assert r.retained == (contact,)


def test_no_target_admission_means_normal_planner_check_even_before_bounce():
    contact = PathContact(140, 12, "move", MOVE)
    r = check(scan(contact), admission=None)
    assert r.verdict == "reject"


def test_guard_for_second_slam_cannot_admit_the_first_even_on_same_monster():
    second = MoveInstance(MOVE.target_iid, 120, MOVE.family)
    guard = TargetMoveAdmission(second, 120, 170, "h2:test:event120", "pass")
    with pytest.raises(ValueError, match="move identity mismatch"):
        check(scan(), admission=guard)


def test_guard_cannot_be_reused_for_another_decision_frame():
    with pytest.raises(ValueError, match="another decision frame"):
        check(scan(), first_frame=101)


@pytest.mark.parametrize("verdict", ["reject", "unchecked"])
def test_guard_not_passed_never_grants_an_empty_path_admission(verdict):
    r = check(scan(), admission=replace(GUARD, verdict=verdict))
    assert r.verdict == verdict


@pytest.mark.parametrize("kind", ["body", "move"])
def test_continuations_check_remaining_current_slam_normally(kind):
    target_contact = PathContact(152, 12, kind, MOVE)
    opts = [option("left", "left_landing", contacts=(target_contact,)),
            option("right", "right_landing")]
    r = assess(opts, lambda o: scan(first=149, last=200, path=o.path_ref))
    assert r.mode == "full_exit"
    assert r.qualifying_kinds == ("right_landing",)
    left = next(x for x in r.checks if x.option_id == "left")
    assert left.path_result.retained == (target_contact,)


def test_complete_exit_includes_targets_next_move():
    next_move = MoveInstance(12, 170, "CC_JUMP")
    contact = PathContact(175, 12, "move", next_move)
    r = assess([option("dash", "dash_out")],
               lambda o: scan(contact, first=149, last=200, path=o.path_ref))
    assert r.verdict == "reject"
    assert r.checks[-1].path_result.retained == (contact,)
