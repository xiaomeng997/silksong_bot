"""Causal contract tests for chain data and the native-adapter boundary."""
from copy import deepcopy
import json

import pytest

from ssbot.combat.knife_chain_format import chains_from_json, load_chains, table_digest, ChainFormatError
from ssbot.combat.knife_chain_admission import Observation, evaluate_admission
from ssbot.combat.knife_chain_dispatch import ChainDispatch


def records():
    return {"slam": {"id": "slam", "start": "walk", "links": {
        "walk": {"id": "slam.walk", "phase": "walk", "keys": [{"mask": "R"}],
                 "rules": [{"do": "try", "to": "air", "when": {"p": "airborne"}}]},
        "air": {"id": "slam.air", "phase": "air", "needs": ["anchor"], "carry": ["sent"],
                "entry": {"p": "airborne"}, "rules": [{"do": "goto", "to": "walk", "mode": "next"}]}},
        "admission": {k: {"link": "slam." + k, "observations": [
            {"name": n, "unit": "u", "source": "STATE"} for n in ("x", "v", "s0")],
            "conditions": [{"kind": "range", "obs": "x", "lo": None, "hi": None},
                           {"kind": "pred", "pred": "region", "params": {}, "fitted": None}]}
                      for k in ("walk", "air")}}}


def fitted():
    a = chains_from_json(records())["slam"].admission["air"]
    a.status = "fitted"
    a.conditions[0].update(lo=4.0, hi=6.0)
    return a


def observations(**values):
    return {k: Observation(v, 100, "STATE:f100") for k, v in values.items()}


def test_roundtrip_and_digest_are_semantic(tmp_path):
    table = chains_from_json(records())
    raw = {k: c.to_json() for k, c in table.items()}
    p = tmp_path / "chain.json"
    p.write_text(json.dumps(raw, indent=3), encoding="utf-8")
    assert {k: c.to_json() for k, c in load_chains(p).items()} == raw
    assert table_digest(load_chains(p)) == table_digest(table)
    changed = deepcopy(table)
    changed["slam"].links["air"].needs.append("pogo_observed")
    assert table_digest(changed) != table_digest(table)


@pytest.mark.parametrize("change,match", [
    (lambda d: d["slam"].update(start="missing"), "start link"),
    (lambda d: d["slam"]["links"]["walk"]["rules"][0].update(to="other.air"), "transition target"),
    (lambda d: d["slam"]["links"]["walk"].update(inherit=["missing"]), "ruleset"),
    (lambda d: d["slam"]["links"]["air"].update(needs=["a", "a"]), "duplicate needs"),
    (lambda d: d["slam"]["links"]["air"].update(id="slam.walk"), "identity"),
    (lambda d: d["slam"]["admission"].pop("air"), "admission record"),
    (lambda d: d["slam"]["links"]["walk"]["keys"][0].update(gen="generate"), "exactly one"),
    (lambda d: d["slam"]["links"]["walk"]["rules"][0].update(do="exec"), "operation"),
    (lambda d: d["slam"]["links"]["air"].update(entry={"p": "x", "any": []}), "one operator"),
    (lambda d: d["slam"].update(cfg={"bad": float("nan")}), "non-finite"),
    (lambda d: d["slam"].update(new_unknown_field=1), "invalid v0 record"),
])
def test_malformed_data_rejected_before_any_primitive(change, match):
    raw = records()
    change(raw)
    with pytest.raises(ChainFormatError, match=match):
        chains_from_json(raw)


def test_duplicate_json_field_rejected(tmp_path):
    p = tmp_path / "duplicate.json"
    p.write_text('{"slam": {}, "slam": {}}')
    with pytest.raises(ChainFormatError, match="duplicate JSON"):
        load_chains(p)


def test_unfitted_and_empty_spaces_are_unknown():
    a = chains_from_json(records())["slam"].admission["air"]
    assert evaluate_admission(a, observations(x=5), frame=100).verdict == "unchecked"
    a.status = "fitted"
    assert evaluate_admission(a, observations(x=5), frame=100, fit_ref="fit:v1").verdict == "unchecked"


def test_unselected_template_features_do_not_become_hidden_requirements():
    a = fitted()
    decision = evaluate_admission(a, observations(x=5), frame=100, fit_ref="fit:v1")
    assert decision.verdict == "pass"  # no H, FREE_MIN, or 270-world requirement
    assert [c.name for c in decision.checks] == ["x"]
    assert evaluate_admission(a, observations(x=7), frame=100, fit_ref="fit:v1").verdict == "reject"
    assert evaluate_admission(a, observations(x=5), frame=100).verdict == "unchecked"


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), "unknown"])
def test_unknown_numeric_features_cannot_pass(value):
    assert evaluate_admission(fitted(), observations(x=value), frame=100, fit_ref="fit:v1").verdict == "unchecked"


def test_causal_cutoff_is_feature_specific():
    a = fitted()
    assert evaluate_admission(a, observations(x=5), frame=100, fit_ref="fit:v1").verdict == "pass"
    assert evaluate_admission(a, observations(x=5), frame=100, fit_ref="fit:v1", cutoffs={"x": 98}).verdict == "unchecked"
    obs = {"x": Observation(5, 98, "history:f98")}
    assert evaluate_admission(a, obs, frame=100, fit_ref="fit:v1", cutoffs={"x": 98}).verdict == "pass"
    with pytest.raises(ValueError, match="future"):
        evaluate_admission(a, obs, frame=100, fit_ref="fit:v1", cutoffs={"x": 101})


def test_correlated_region_and_predicate_defects():
    a = fitted()
    a.conditions[1].update(params={"observations": ["x", "v"]}, fitted={"max_sum": 6})
    def region(values, params, fit):
        return values["x"] + values["v"] <= fit["max_sum"]
    kwargs = {"frame": 100, "fit_ref": "fit:v1", "predicates": {"region": region}}
    assert evaluate_admission(a, observations(x=5, v=1), **kwargs).verdict == "pass"
    assert evaluate_admission(a, observations(x=5, v=2), **kwargs).verdict == "reject"
    assert evaluate_admission(a, observations(x=5), **kwargs).verdict == "unchecked"
    assert evaluate_admission(a, observations(x=5, v=1), frame=100, fit_ref="fit:v1").verdict == "unchecked"
    kwargs["predicates"] = {"region": lambda *args: 1 / 0}
    with pytest.raises(ZeroDivisionError):
        evaluate_admission(a, observations(x=5, v=1), **kwargs)


def offer(dispatch, *, a=None):
    a = a or fitted()
    decision = evaluate_admission(a, observations(x=5), frame=dispatch.frame, fit_ref="fit:v1")
    return dispatch.offer(a.link, 3, table_ref="table:v0", admission=decision)


def test_preview_and_selection_do_not_claim_send_or_latch():
    dispatch = ChainDispatch()
    dispatch.begin_tick(100)
    candidate = offer(dispatch)
    assert dispatch.queued(after=99) == ()
    selected = dispatch.select(candidate)
    assert selected.mode == "fitted" and dispatch.queued(after=99) == ()
    # Transport fails / another row wins: no receipt, no invented sent key.
    dispatch.begin_tick(101)
    assert dispatch.queued(after=99) == ()
    with pytest.raises(ValueError, match="stale"):
        dispatch.select(candidate)


def test_unfitted_exploration_remains_labelled_probe():
    dispatch = ChainDispatch()
    dispatch.begin_tick(100)
    candidate = offer(dispatch, a=chains_from_json(records())["slam"].admission["air"])
    with pytest.raises(ValueError, match="probe"):
        dispatch.select(candidate)
    selection = dispatch.select(candidate, probe_ref="protocol:bounded-w7-experiment")
    assert selection.mode == "probe"
    assert selection.offer.admission.verdict == "unchecked"


def test_actual_hold_mask_and_sent_prefix_are_preserved():
    dispatch = ChainDispatch()
    dispatch.begin_tick(100)
    candidate = offer(dispatch)
    dispatch.select(candidate)
    sent = dispatch.record_send(frame=100, target_frame=102, desired_mask=3, wire_mask=2, owner=candidate.owner)
    assert sent.chain_outcome == "sent"
    assert dispatch.queued(after=101) == (sent,)
    assert dispatch.observe(observed_frame=103, target_frame=102, mask=2).outcome == "match"
    with pytest.raises(ValueError, match="already sent"):
        dispatch.record_send(frame=100, target_frame=102, desired_mask=0, wire_mask=0, owner="planner")
    with pytest.raises(ValueError, match="conflicting latch"):
        dispatch.observe(observed_frame=104, target_frame=102, mask=3)


def test_same_mask_from_supervisor_is_an_override_not_chain_ownership():
    dispatch = ChainDispatch()
    dispatch.begin_tick(100)
    candidate = offer(dispatch)
    dispatch.select(candidate)
    sent = dispatch.record_send(frame=100, target_frame=102, desired_mask=3, wire_mask=3, owner="supervisor")
    assert sent.chain_outcome == "overridden"
    assert dispatch.observe(observed_frame=102, target_frame=102, mask=0).outcome == "differs"


def test_missing_wire_fact_is_not_assumed_to_be_desired():
    dispatch = ChainDispatch()
    dispatch.begin_tick(100)
    sent = dispatch.record_send(frame=100, target_frame=102, desired_mask=3, wire_mask=None, owner="planner")
    assert sent.chain_outcome == "unselected"
    assert dispatch.observe(observed_frame=102, target_frame=102, mask=3).outcome == "wire_unchecked"


def test_foreign_offer_and_fake_chain_send_rejected():
    one, two = ChainDispatch(), ChainDispatch()
    one.begin_tick(100)
    two.begin_tick(100)
    with pytest.raises(ValueError, match="another dispatch"):
        two.select(offer(one))
    with pytest.raises(ValueError, match="without a selection"):
        two.record_send(frame=100, target_frame=102, desired_mask=3, wire_mask=3, owner="knife_chain:slam.air")
    with pytest.raises(ValueError, match="causal send"):
        two.observe(observed_frame=102, target_frame=102, mask=3)


def test_predicate_preview_cannot_mutate_observed_or_fitted_context():
    a = fitted()
    a.conditions = [{"kind": "pred", "pred": "region", "params": {"observations": ["s0"]},
                     "fitted": {"region": [1, 2]}}]
    actual = {"s0": Observation({"times": [90, 91]}, 99, "observed_history")}
    before_a, before_actual = deepcopy(a), deepcopy(actual)
    def mutate(values, params, fit):
        values["s0"]["times"].append(999)
        params["observations"].clear()
        fit["region"].clear()
        return True
    assert evaluate_admission(a, actual, frame=100, fit_ref="fit:v1",
                              predicates={"region": mutate}).verdict == "pass"
    assert a == before_a and actual == before_actual


@pytest.mark.parametrize("bad,match", [
    ({"clock": "antci"}, "unknown clock"),
    ({"keys": [{"mask": "R", "clock": "jumpp"}]}, "unknown clock"),
    ({"keys": [{"mask": "D|ATTACK"}]}, "mask name"),
    ({"keys": [{"mask": "D||A"}]}, "mask name"),
    ({"keys": [{"mask": -1}]}, "mask specification"),
    ({"keys": [{"mask": True}]}, "mask specification"),
    ({"keys": [{"mask": 1.5}]}, "mask specification"),
    ({"rules": [{"do": "try", "to": "air", "orelse": "continue"}]}, "orelse"),
    ({"rules": [{"do": "set", "orelse": "hold"}]}, "orelse"),
    ({"rules": [{"do": "set", "set": {"count": "cfg.delai"}}]}, "cfg reference"),
    ({"rules": [{"do": "set", "pre": {"count": "var.coutn"}}]}, "var reference"),
    ({"rules": [{"do": "set", "set": {"coutn": 2}}]}, "undeclared var"),
    ({"rules": [{"do": "set", "set": {"count": {"sub": [1]}}}]}, "sub operands"),
    ({"rules": [{"do": "set", "set": {"count": {"min": []}}}]}, "min operands"),
    ({"rules": [{"do": "set", "set": {"count": {"add": [1], "sub": [1, 2]}}}]}, "one operator"),
    ({"rules": [{"do": "set", "set": {"count": {"ad": [1, 2]}}}]}, "one operator"),
    ({"rules": [{"do": "set", "set": {"count": "clk.antci"}}]}, "unknown clock"),
    ({"rules": [{"do": "goto", "to": "air", "mode": "emit"}]}, "requires a mask"),
    ({"rules": [{"do": "goto", "to": "air", "mode": "emit", "emit": "D|BOGUS"}]}, "mask name"),
    ({"rules": [{"do": "goto", "to": "air", "mode": "emit", "emit": {"keys": "other"}}]}, "keys must"),
    ({"rules": [{"do": "goto", "to": "air", "mode": "emit", "emit": {"or": "A"}}]}, "or needs"),
    ({"rules": [{"do": "goto", "to": "air", "mode": "emit", "emit": {"keys": "self", "only": "jump"}}]}, "component selection"),
    ({"rules": [{"do": "goto", "to": "air", "mode": "emit", "emit": {"keys": "self", "extra": 1}}]}, "mask specification"),
    ({"entry": {"p": "cmp", "a": {"add": ["var.coutn", 1]}}}, "var reference"),
    ({"keys": [{"gen": "test", "args": {"n": "cfg.delai"}}]}, "cfg reference"),
])
def test_table_syntax_errors_fail_at_load(bad, match):
    raw = records()
    raw["slam"]["vars"] = {"count": 0}
    raw["slam"]["cfg"] = {"delay": 2}
    raw["slam"]["links"]["walk"].update(bad)
    with pytest.raises(ChainFormatError, match=match):
        chains_from_json(raw)


def test_expression_syntax_and_literals_survive_roundtrip():
    raw = records()
    raw["slam"]["vars"] = {"count": 0}
    raw["slam"]["cfg"] = {"delay": 2}
    link = raw["slam"]["links"]["walk"]
    link["rules"] = [
        {"do": "set", "pre": {"count": {"add": ["cfg.delay", {"sub": ["var.count", 1]}]}},
         "set": {"count": {"fn": "pick", "values": [{"min": [1, 2]}, {"max": [2, 3]}]}}},
        {"do": "goto", "to": "air", "mode": "emit", "emit": {"keys": "self", "only": ["absent_variant_key"],
                                                               "or": ["D|A", "toward"]}},
        {"do": "set", "why": "cfg.this_is_a_literal_reason", "set": {"count": {"lit": {"key": "var.literal"}}}},
    ]
    table = chains_from_json(raw)
    # only is a filter, not a required component: original v0 air uses this.
    assert table["slam"].links["walk"].rules[1].emit["only"] == ["absent_variant_key"]
    again = {k: v.to_json() for k, v in table.items()}
    assert {k: v.to_json() for k, v in chains_from_json(again).items()} == again


def test_family_adapter_can_supply_its_registered_vocabulary(tmp_path):
    from ssbot.combat.knife_chain_format import ChainVocabulary
    raw = records()
    raw["slam"]["links"]["walk"].update(clock="idle", keys=[{"mask": "facing"}])
    with pytest.raises(ChainFormatError, match="unknown clock"):
        chains_from_json(raw)
    vocab = ChainVocabulary(clocks=frozenset({"antic", "idle"}), directions=frozenset({"facing"}))
    table = chains_from_json(raw, vocabulary=vocab)
    path = tmp_path / "chain.json"
    path.write_text(json.dumps({k: c.to_json() for k, c in table.items()}))
    assert table_digest(load_chains(path, vocabulary=vocab), vocabulary=vocab) == table_digest(table, vocabulary=vocab)


@pytest.mark.parametrize("unfitted", [False, True])
def test_misspelled_cutoff_is_rejected_even_before_fitting(unfitted):
    a = fitted()
    if unfitted:
        a.status = "unfitted"
    with pytest.raises(ValueError, match="undeclared observation"):
        evaluate_admission(a, observations(x=5), frame=100, fit_ref="fit:v1", cutoffs={"xx": 98})


def test_episode_reset_drops_history_and_invalidates_old_offers():
    d = ChainDispatch()
    d.begin_tick(100)
    old = offer(d)
    d.select(old)
    d.record_send(frame=100, target_frame=102, desired_mask=3, wire_mask=2, owner=old.owner)
    d.observe(observed_frame=102, target_frame=102, mask=2)
    d.reset()
    assert d.frame is None and d.selection is None and d.queued(after=0) == ()
    with pytest.raises(ValueError, match="causal send"):
        d.observe(observed_frame=102, target_frame=102, mask=2)
    d.begin_tick(100)  # The new game's frame numbers may restart.
    fresh = offer(d)
    with pytest.raises(ValueError, match="stale"):
        d.select(old)
    d.select(fresh)
    sent = d.record_send(frame=100, target_frame=102, desired_mask=3, wire_mask=3, owner=fresh.owner)
    assert d.observe(observed_frame=102, target_frame=102, mask=3).sent is sent
    d.reset()
    d.reset()
    d.begin_tick(1)
    assert d.queued(after=0) == ()
