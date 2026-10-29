"""The declared world domain must be complete before any hit path is integrated."""
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import pytest
from ssbot.combat import forum_knife_hit as hit, forum_knife_coupled as coupled, forum_knife as knife
from tests.test_forum_knife_worlds import case  # noqa: F401


def invoke(case, worlds=None, expected=None, **kwargs):
    planner, all_worlds, raw, hold, _ = case
    planner._esc_cmds = lambda n: np.zeros((1, n), np.int64)
    worlds = all_worlds if worlds is None else worlds
    expected = tuple(w.key for w in all_worlds) if expected is None else expected
    return hit.common_escape(planner, worlds, raw, hold, horizon=37, expected_worlds=expected, **kwargs)


@pytest.mark.parametrize("change", ["missing", "extra", "same_count_wrong_key"])
def test_a_missing_or_substituted_world_refuses_before_integrating(case, change):
    planner, worlds, raw, hold, _ = case
    expected = tuple(w.key for w in worlds)
    def forbidden(*args): raise AssertionError("domain gate must run before any rollout")
    worlds = [replace(w, reroll=forbidden) for w in worlds]
    if change == "missing": worlds = worlds[:1]
    if change == "extra": worlds += [replace(worlds[0], key=(7, (47,4,3,4,14), 0))]
    if change == "same_count_wrong_key": worlds[1] = replace(worlds[1], key=(7, (49,4,3,4,14), 1))
    audit = {}
    with pytest.raises(ValueError, match="world domain mismatch"):
        hit.common_escape(planner, worlds, raw, hold, horizon=37, expected_worlds=expected, audit=audit)
    assert audit["status"] == "unchecked" and audit["reason"] == "target_world_domain_mismatch"
    assert audit["missing_worlds"] or audit["extra_worlds"]


@pytest.mark.parametrize("bad", [None, (), ((7,(47,4,3,4,14),0),)*2, ("untyped",)])
def test_expected_domain_is_required_nonempty_unique_and_typed(case, bad):
    planner, worlds, raw, hold, _ = case
    with pytest.raises(ValueError):
        hit.common_escape(planner, worlds, raw, hold, horizon=37, expected_worlds=bad)
    with pytest.raises(TypeError, match="expected_worlds"):
        hit.common_escape(planner, worlds, raw, hold, horizon=37)


@pytest.mark.parametrize("bad", [None, {}, {"iid":7,"shift":-1}, {"iid":7,"durations":None,"shift":-1}])
def test_paired_forecast_marker_cannot_be_omitted(case, bad):
    case[1][0].forecast.rs.knife_coupled_world = bad
    with pytest.raises(ValueError, match="paired forecast target world marker"):
        invoke(case)


def test_forecast_of_another_timing_world_is_not_an_allowed_substitution(case):
    case[1][0].forecast.rs.knife_coupled_world["shift"] = 0
    with pytest.raises(ValueError, match="forecast target world identity mismatch"):
        invoke(case)


def test_complete_domain_order_does_not_change_its_identity_or_result(case):
    expected = tuple(w.key for w in case[1]); a = {}; b = {}
    ca = invoke(case, expected=expected, audit=a)
    cb = invoke(case, worlds=list(reversed(case[1])), expected=tuple(reversed(expected)), audit=b)
    assert ca.option == cb.option == 0 and ca.start == cb.start
    assert ca.expected_world_keys == cb.expected_world_keys == tuple(sorted(expected))
    assert a["expected_world_count"] == 2
    assert a["expected_world_sha256"] == b["expected_world_sha256"]


def test_canonical_domain_uses_all_model_durations_and_shifts_before_contact():
    knowledge = knife.cm.Know.load()
    observation = SimpleNamespace(iid=7, st="Slam Antic", j=1, x=25., y=7., face=-1)
    reference = coupled.expected_slam_worlds(observation, knowledge)
    # Independent of which worlds any proposed row happens to hit.
    paths = [np.tile([24.,3.,26.,8.], (3,1))]
    body_keys = {(7, tuple(d), shift) for d, _ in knife.slam_body_variants(observation, paths, knowledge)
                 for shift in (-2,-1,0,1,2)}
    assert set(reference) == body_keys and len(reference) == 270
    observation.j = 48
    assert all(key[1][0] > observation.j for key in coupled.expected_slam_worlds(observation, knowledge))


@pytest.mark.parametrize("bad", [None, (0,1,2), (3,2,1), (1.,1.,1.)])
def test_unknown_or_invalid_duration_domain_is_never_assumed_complete(bad):
    knowledge = SimpleNamespace(durations=lambda state: bad)
    with pytest.raises(ValueError, match="duration domain"):
        coupled.expected_slam_worlds(SimpleNamespace(iid=7, st="Slam Antic", j=1), knowledge)


def test_new_entry_rule_still_refuses_when_the_same_absolute_strike_enters_H(case):
    world = case[1][0]
    seen = []
    for age in range(20):
        base = SimpleNamespace(hooks=world.base.hooks, control_frames=np.array([20-age]))
        shifted = replace(world, base=base, swing=np.array([43-age]),
                          first=np.array([47-age]), last=np.array([47-age]))
        P, T = 1+age%2, 36
        H = P+T
        good = hit.contacts_fit(shifted, H, 80-age)
        assert good == (47 > age+H)
        seen.append(good)
    assert all(seen[:9]) and not any(seen[9:])
    # This is deliberately a NEW-entry boundary test, not a continuation proof.
    # Per-tick hit-only continuation requires actual send/clock/state lineage.
