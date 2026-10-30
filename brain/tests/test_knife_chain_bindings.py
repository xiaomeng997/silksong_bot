"""A rare chain branch must fail binding, not fail on its first live execution."""
from copy import deepcopy
from types import SimpleNamespace
import json

import pytest

from ssbot.combat.knife_chain_bindings import bind_chains, load_bound_chains
from ssbot.combat.knife_chain_format import chains_from_json, ChainFormatError
from tests.test_knife_chain import records


def never_execute(*args, **kwargs):
    raise AssertionError("binding must not execute primitives")


def registry():
    return SimpleNamespace(guards={"airborne": never_execute, "compare": never_execute},
                           acts={"mark": never_execute}, gens={"steer": never_execute},
                           values={"position": never_execute}, dirs={"toward": never_execute})


def sample():
    raw = records()
    c = raw["slam"]
    c["vars"] = {"anchor": 0}
    c["cfg"] = {"delay": 2}
    l = c["links"]["walk"]
    l["entry"] = {"all": [{"p": "airborne"}, {"not": {"p": "compare", "value": "obs.vy"}}]}
    l["keys"] = [{"gen": "steer", "args": {"x": {"fn": "position", "now": "k"}}, "lo": "cfg.delay"}]
    l["rules"] = [{"do": "set", "set": {"anchor": "var.anchor"}, "act": {"a": "mark", "value": "obs.x"}},
                  {"do": "goto", "to": "air", "mode": "emit", "emit": "toward|A"}]
    return raw


def bind(raw, **kwargs):
    return bind_chains(chains_from_json(raw), primitives=registry(), observation_names={"x", "vy"}, **kwargs)


def test_full_binding_never_executes_registry_and_preserves_records(tmp_path):
    raw = sample()
    original = deepcopy(raw)
    p = tmp_path / "chain.json"
    p.write_text(json.dumps(raw))
    chains, report = load_bound_chains(p, primitives=registry(), observation_names={"x", "vy"})
    assert raw == original
    assert report["used"] == {"guards": ["airborne", "compare"], "acts": ["mark"], "gens": ["steer"],
                               "values": ["position"], "dirs": ["toward"], "observations": ["vy", "x"], "literals": []}
    assert {k: c.to_json() for k, c in chains.items()} == {k: c.to_json() for k, c in chains_from_json(raw).items()}


@pytest.mark.parametrize("group", ["guards", "acts", "gens", "values", "dirs"])
def test_missing_actual_registration_rejected(group):
    prims = registry()
    getattr(prims, group).clear()
    with pytest.raises(ChainFormatError, match="unregistered " + group):
        bind_chains(chains_from_json(sample()), primitives=prims, observation_names={"x", "vy"})


@pytest.mark.parametrize("change", [
    lambda l: l.update(entry={"p": "compare", "value": "obs.hx_typo"}),
    lambda l: l["keys"][0].update(lo="obs.hx_typo"),
    lambda l: l["keys"][0].update(args={"x": {"fn": "position", "arg": ["obs.hx_typo"]}}),
    lambda l: l["rules"][0]["act"].update(value="obs.hx_typo"),
    lambda l: l["rules"][0]["set"].update(anchor="obs.hx_typo"),
    lambda l: l.update(post=[{"do": "done", "when": {"p": "compare", "value": "obs.hx_typo"}}]),
])
def test_observation_names_are_bound_in_every_expression_context(change):
    raw = sample()
    change(raw["slam"]["links"]["walk"])
    with pytest.raises(ChainFormatError, match="unregistered observation"):
        bind(raw)


@pytest.mark.parametrize("value", ["cgf.delay", "vra.anchor", "clik.press", "osb.x", "arbitrary text"])
def test_prefix_typos_are_not_accidental_literals(value):
    raw = sample()
    raw["slam"]["links"]["walk"]["rules"][0]["set"]["anchor"] = value
    # The compatibility reader retains the historical v0 expression semantics.
    chains_from_json(raw)
    with pytest.raises(ChainFormatError, match="undeclared bare literal"):
        bind(raw)


def test_registered_small_literal_set_and_explicit_lit_are_distinct():
    raw = sample()
    l = raw["slam"]["links"]["walk"]
    l["entry"] = {"p": "compare", "value": "Slam Antic"}
    l["rules"][0]["set"]["anchor"] = {"lit": {"cfg": "cgf.literal", "fn": "not_a_function"}}
    l["rules"][0]["why"] = "ordinary diagnostic text is not an expression"
    with pytest.raises(ChainFormatError, match="bare literal"):
        bind(raw)
    report = bind(raw, literal_names={"Slam Antic"})
    assert report["used"]["literals"] == ["Slam Antic"]
    assert "not_a_function" not in report["used"]["values"]


def test_unused_link_and_unused_ruleset_are_bound_before_runtime():
    raw = sample()
    raw["slam"]["links"]["air"]["entry"] = {"p": "typo"}
    with pytest.raises(ChainFormatError, match="unregistered guards"):
        bind(raw)
    raw = sample()
    raw["slam"]["rulesets"] = {"future": [{"do": "act", "act": {"a": "typo"}}]}
    with pytest.raises(ChainFormatError, match="unregistered acts"):
        bind(raw)


def test_each_family_supplies_context_names_not_admission_features():
    raw = sample()
    # These are derived admission features, not fields of the interpreter Obs.
    raw["slam"]["admission"]["walk"]["observations"].append({"name": "computed_box_gap"})
    assert "computed_box_gap" not in bind(raw)["used"]["observations"]


@pytest.mark.parametrize("group", ["guards", "acts", "gens", "values", "dirs"])
def test_noncallable_registration_is_rejected(group):
    prims = registry()
    getattr(prims, group)["accidental_data"] = 1
    with pytest.raises(ChainFormatError, match="named callables"):
        bind_chains(chains_from_json(sample()), primitives=prims, observation_names={"x", "vy"})


def test_toward_direction_must_be_registered_even_though_syntax_allows_it():
    prims = registry()
    prims.dirs = {}
    with pytest.raises(ChainFormatError, match="unregistered dirs"):
        bind_chains(chains_from_json(sample()), primitives=prims, observation_names={"x", "vy"})
