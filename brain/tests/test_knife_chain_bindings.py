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
    return bind_chains(chains_from_json(raw), primitives=registry(), observation_names={"x", "vy"}, context_names={"sent"}, **kwargs)


def test_full_binding_never_executes_registry_and_preserves_records(tmp_path):
    raw = sample()
    original = deepcopy(raw)
    p = tmp_path / "chain.json"
    p.write_text(json.dumps(raw))
    chains, report = load_bound_chains(p, primitives=registry(), observation_names={"x", "vy"}, context_names={"sent"})
    assert raw == original
    assert report["used"] == {"guards": ["airborne", "compare"], "acts": ["mark"], "gens": ["steer"],
                               "values": ["position"], "dirs": ["toward"], "observations": ["vy", "x"], "literals": []}
    assert {k: c.to_json() for k, c in chains.items()} == {k: c.to_json() for k, c in chains_from_json(raw).items()}


@pytest.mark.parametrize("group", ["guards", "acts", "gens", "values", "dirs"])
def test_missing_actual_registration_rejected(group):
    prims = registry()
    getattr(prims, group).clear()
    with pytest.raises(ChainFormatError, match="unregistered " + group):
        bind_chains(chains_from_json(sample()), primitives=prims, observation_names={"x", "vy"}, context_names={"sent"})


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
        bind_chains(chains_from_json(sample()), primitives=prims, observation_names={"x", "vy"}, context_names={"sent"})


def test_toward_direction_must_be_registered_even_though_syntax_allows_it():
    prims = registry()
    prims.dirs = {}
    with pytest.raises(ChainFormatError, match="unregistered dirs"):
        bind_chains(chains_from_json(sample()), primitives=prims, observation_names={"x", "vy"}, context_names={"sent"})


@pytest.mark.parametrize("field", ["needs", "carry"])
@pytest.mark.parametrize("name", ["anchro", "sn et", "snet"])
def test_cut_in_field_typos_fail_binding_instead_of_silent_refusal(field, name):
    raw = sample()
    raw["slam"]["links"]["air"][field] = [name]
    with pytest.raises(ChainFormatError, match="unbound " + field):
        bind(raw)


def test_cut_in_names_need_independent_declaration_and_values_can_be_unknown():
    raw = sample()
    raw["slam"]["vars"]["anchor"] = None
    chains = chains_from_json(raw)
    with pytest.raises(ChainFormatError, match="unbound carry"):
        bind_chains(chains, primitives=registry(), observation_names={"x", "vy"})
    report = bind(raw)
    assert report["entry_fields"] == {"slam": {"needs": ["anchor"], "carry": ["sent"], "adapter": ["sent"]}}
    # Declaration only: no fake value is supplied, no admission/entry is run.
    assert chains["slam"].vars["anchor"] is None


def test_variable_in_another_chain_does_not_declare_this_entry_field():
    raw = sample()
    raw["slam"]["links"]["air"]["needs"] = ["other_only"]
    other = deepcopy(raw["slam"])
    other["id"] = "other"
    other["vars"]["other_only"] = 0
    other["links"]["air"]["needs"] = ["anchor"]
    for key, link in other["links"].items():
        link["id"] = "other." + key
    for key, admission in other["admission"].items():
        admission["link"] = "other." + key
    raw["other"] = other
    with pytest.raises(ChainFormatError, match="unbound needs"):
        bind(raw)


def test_observation_name_does_not_implicitly_declare_cut_in_context():
    raw = sample()
    raw["slam"]["links"]["air"]["carry"] = ["vy"]
    with pytest.raises(ChainFormatError, match="unbound carry"):
        bind(raw)


@pytest.mark.parametrize("context_names", ["sent", {"bad name"}])
def test_adapter_context_declaration_must_be_a_collection_of_field_names(context_names):
    with pytest.raises(ChainFormatError):
        bind_chains(chains_from_json(sample()), primitives=registry(), observation_names={"x", "vy"},
                    context_names=context_names)
