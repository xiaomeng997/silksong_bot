"""Bind chain data to a real family registry before any link executes.

Structural loading remains compatible with reviewed v0. Native family adapters
should use load_bound_chains (or bind_chains immediately after loading) so typos
cannot wait for the first execution of a rare branch. This checks names, not
callable semantics, causal state reconstruction or empirical admission.
"""
from __future__ import annotations

from collections.abc import Mapping

from .knife_chain_format import (
    DEFAULT_VOCABULARY, MASK_NAMES, ChainFormatError, ChainVocabulary,
    load_chains, table_digest, validate_chains,
)


def bind_chains(chains, *, primitives, observation_names, literal_names=(),
                vocabulary: ChainVocabulary = DEFAULT_VOCABULARY):
    """Validate ALL links/rulesets against the family's actual callable maps.

    primitives exposes guards/acts/gens/values/dirs, matching the v0 registry.
    observation_names are interpreter-context attributes, not the separately
    derived empirical Admission features. A string expression is either a known
    reference, the antic shorthand k, or an explicitly registered literal. Use
    {"lit": value} for other literal payloads. Structural fields (id, phase, to,
    note, scalar why, key names) are not expressions and retain their grammar.

    No primitive is called. The returned audit summary confers no runtime/safety
    certificate; record the family's source/version separately in the manifest.
    """
    validate_chains(chains, vocabulary=vocabulary)
    registry = {}
    for name in ("guards", "acts", "gens", "values", "dirs"):
        values = getattr(primitives, name, None)
        if not isinstance(values, Mapping):
            raise ChainFormatError(f"missing {name} registry")
        if any(not isinstance(k, str) or not k or not callable(v) for k, v in values.items()):
            raise ChainFormatError(f"{name}: registry entries must be named callables")
        registry[name] = dict(values)
    if isinstance(observation_names, str) or isinstance(literal_names, str):
        raise ChainFormatError("observation/literal names must be collections, not strings")
    observations, literals = frozenset(observation_names), frozenset(literal_names)
    if any(not isinstance(n, str) or not n.isidentifier() for n in observations):
        raise ChainFormatError("invalid registered observation name")
    if any(not isinstance(n, str) for n in literals):
        raise ChainFormatError("literal names must be strings")
    used = {name: set() for name in (*registry, "observations", "literals")}

    def require(group, name, where):
        if name not in registry[group]:
            raise ChainFormatError(f"{where}: unregistered {group} name {name!r}")
        used[group].add(name)

    def expr(value, where):
        if isinstance(value, str):
            if value.startswith("obs."):
                name = value[4:]
                if name not in observations:
                    raise ChainFormatError(f"{where}: unregistered observation {name!r}")
                used["observations"].add(name)
            elif value == "k" or value.startswith(("cfg.", "var.", "clk.")):
                pass  # Structural loader already checked these references.
            elif value in literals:
                used["literals"].add(value)
            else:
                raise ChainFormatError(f"{where}: undeclared bare literal {value!r}; use lit for literal data")
        elif isinstance(value, list):
            for child in value:
                expr(child, where)
        elif isinstance(value, dict):
            if "lit" in value:
                return  # The interpreter does not resolve anything inside lit.
            if "fn" in value:
                require("values", value["fn"], where)
                for key, arg in value.items():
                    if key != "fn":
                        expr(arg, where)
            else:
                for args in value.values():
                    expr(args, where)

    def guard(value, where):
        if value is None:
            return
        if "p" in value:
            require("guards", value["p"], where)
            for key, arg in value.items():
                if key != "p":
                    expr(arg, where)
        elif "not" in value:
            guard(value["not"], where)
        else:
            for child in value.get("all", value.get("any", [])):
                guard(child, where)

    def mask(value, where):
        if isinstance(value, str):
            for name in value.split("|"):
                name = name.strip()
                if name not in MASK_NAMES:
                    require("dirs", name, where)
        elif isinstance(value, dict):
            for child in value.get("or", []):
                mask(child, where)

    def rule(value, where):
        guard(value.when, where)
        for assignment in (value.set, value.pre):
            for arg in assignment.values():
                expr(arg, where)
        if value.act is not None:
            require("acts", value.act["a"], where)
            for key, arg in value.act.items():
                if key != "a":
                    expr(arg, where)
        if isinstance(value.why, dict):
            expr(value.why, where)
        if value.emit is not None:
            mask(value.emit, where)

    for chain in chains.values():
        for name, rules in chain.rulesets.items():
            for value in rules:
                rule(value, chain.id + ".rulesets." + name)
        for link in chain.links.values():
            where = link.id
            guard(link.entry, where)
            for comp in link.keys:
                guard(comp.when, where)
                for value in (comp.lo, comp.hi, *comp.args.values()):
                    expr(value, where)
                if comp.gen is not None:
                    require("gens", comp.gen, where)
                else:
                    mask(comp.mask, where)
            for rules in (link.rules, link.after_keys, link.post):
                for value in rules:
                    rule(value, where)
    return {"table_digest": table_digest(chains, vocabulary=vocabulary),
            "used": {name: sorted(values) for name, values in used.items()}}


def load_bound_chains(path, *, primitives, observation_names, literal_names=(),
                      vocabulary: ChainVocabulary = DEFAULT_VOCABULARY):
    """Family entry point: load, bind all names, then return data and audit summary.

    Bind BEFORE starting an interpreter. Neither loading function executes links
    or changes the wire format. Existing load_chains remains the structural-only
    reader for legacy intake and offline comparisons.
    """
    chains = load_chains(path, vocabulary=vocabulary)
    report = bind_chains(chains, primitives=primitives, observation_names=observation_names,
                         literal_names=literal_names, vocabulary=vocabulary)
    return chains, report
