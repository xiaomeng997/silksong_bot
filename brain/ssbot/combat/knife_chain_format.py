"""Knife-chain v0 records shared with the reviewed offline prototype.

Only records and structural validation live here. Loading a table does not fit
its admission, simulate a link, or confer control of the keyboard. The wire
format is Opus' slam_play_chains_v0.json (two chains, fourteen links).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

SEND_AHEAD = 2

MASK_NAMES = {"J": 1 << 0, "A": 1 << 1, "DASH": 1 << 2, "CLAW": 1 << 4, "U": 1 << 18, "D": 1 << 19, "L": 1 << 20,
              "R": 1 << 21}


@dataclass(frozen=True)
class ChainVocabulary:
    """Syntax supplied by the anchor adapter, not extra fields in rule data.

    Defaults match the reviewed v0 SlamAnchor clocks/directions. Other families
    must supply their actual registered names instead of widening the JSON.
    Callable primitive resolution remains the family adapter's responsibility.
    """
    clocks: frozenset[str] = frozenset({"antic", "s0", "press", "jump", "turn", "mask",
                                       "claw_press", "strike_press"})
    directions: frozenset[str] = frozenset({"toward", "side", "turn_key", "over"})


DEFAULT_VOCABULARY = ChainVocabulary()


# ---- the format ------------------------------------------------------------------------------------------------

@dataclass
class Rule:
    do: str                                  # set | act | keys | hold | abort | done | goto | try
    when: dict | None = None                 # guard (None: always)
    to: str | None = None                    # goto / try target ("chain.link" or "link": same chain)
    mode: str = "same"                       # goto: same | keys | next | emit
    emit: Any = None                         # mode emit: a mask spec (see KeyComp.mask) or {"keys": "self", "or": ..}
    set: dict = field(default_factory=dict)  # var -> expression, applied when the rule fires (try: on entry)
    pre: dict = field(default_factory=dict)  # var -> expression, applied when the guard holds, before act / try
    act: dict | None = None                  # {"a": name, **args}: an action primitive (before set / goto)
    why: Any = None                          # hold / abort / done reason; try: the reason passed to the entry
    orelse: str | None = None                # try: "hold" = no key this tick when the entry fails (else: next rule)
    note: str = ""


@dataclass
class KeyComp:
    mask: Any = None                         # "J" / "D|A" / "toward" / "turn_key" / "side" / "over" / an int
    gen: str | None = None                   # or a generator primitive's name
    args: dict = field(default_factory=dict)
    clock: str = "antic"                     # the window's timer basis
    lo: Any = None                           # window lo / hi on that clock (inclusive; None: open)
    hi: Any = None
    when: dict | None = None                 # an extra guard
    name: str = ""


@dataclass
class Link:
    id: str
    phase: str
    entry: dict | None = None
    needs: list = field(default_factory=list)
    carry: list = field(default_factory=list)
    clock: str = "antic"
    keys: list = field(default_factory=list)
    rules: list = field(default_factory=list)
    after_keys: list = field(default_factory=list)
    post: list = field(default_factory=list)
    ends: list = field(default_factory=list)
    inherit: list = field(default_factory=list)  # rule sets (Chain.rulesets) evaluated before the own rules
    provenance: dict = field(default_factory=dict)


@dataclass
class Admission:
    """The flexible admission space of one link: what it may condition on; the bounds are fitted later (simulation
    or live measurement). Never read by the interpreter; never the old strict safety contract."""
    link: str
    observations: list                       # [{"name", "unit", "source"}]
    conditions: list                         # [{"obs" | "pred", "kind": "range" | "pred", "lo": None, "hi": None}]
    fit_by: list = field(default_factory=lambda: ["simulation", "live"])
    status: str = "unfitted"
    notes: str = ""


@dataclass
class Chain:
    id: str
    start: str
    links: dict                              # link name -> Link
    anchor: dict = field(default_factory=dict)
    rulesets: dict = field(default_factory=dict)
    vars: dict = field(default_factory=dict)
    cfg: dict = field(default_factory=dict)
    admission: dict = field(default_factory=dict)   # link name -> Admission
    provenance: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        def enc(o):
            if hasattr(o, "__dataclass_fields__"):
                return {k: enc(v) for k, v in asdict(o).items()}
            if isinstance(o, dict):
                return {str(k): enc(v) for k, v in o.items()}
            if isinstance(o, (list, tuple)):
                return [enc(v) for v in o]
            return o
        return enc(self)


def link_from_json(d: dict) -> Link:
    d = dict(d)
    d["keys"] = [KeyComp(**k) for k in d.get("keys", [])]
    for k in ("rules", "after_keys", "post"):
        d[k] = [Rule(**r) for r in d.get(k, [])]
    return Link(**d)


def chain_from_json(d: dict) -> Chain:
    d = dict(d)
    d["links"] = {k: link_from_json(v) for k, v in d["links"].items()}
    d["rulesets"] = {k: [Rule(**r) for r in v] for k, v in d.get("rulesets", {}).items()}
    d["admission"] = {k: Admission(**v) for k, v in d.get("admission", {}).items()}
    return Chain(**d)


# The interpreter remains a separate consumer of these records.
class ChainFormatError(ValueError):
    """Malformed records, distinct from a candidate outside a fitted region."""


def _fail(message: str) -> None:
    raise ChainFormatError(message)


def _json_finite(value, path="table") -> None:
    import math
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail(f"{path}: non-finite number")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _json_finite(item, f"{path}[{i}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                _fail(f"{path}: keys must be strings")
            _json_finite(item, f"{path}.{key}")
    else:
        _fail(f"{path}: not JSON data")


def _guard(g, where):
    if g is None:
        return
    if not isinstance(g, dict):
        _fail(f"{where}: guard must be an object")
    ops = set(g) & {"p", "all", "any", "not"}
    if len(ops) != 1:
        _fail(f"{where}: guard needs one operator")
    op = next(iter(ops))
    if op == "p":
        if not isinstance(g[op], str) or not g[op]:
            _fail(f"{where}: predicate name missing")
    elif op == "not":
        if set(g) != {op}:
            _fail(f"{where}: unexpected guard fields")
        _guard(g[op], where)
    else:
        if set(g) != {op} or not isinstance(g[op], list):
            _fail(f"{where}: invalid guard operands")
        for child in g[op]:
            _guard(child, where)


def _clock(name, vocabulary, where):
    if not isinstance(name, str) or name not in vocabulary.clocks:
        _fail(f"{where}: unknown clock {name!r}")


def _expr(value, chain, vocabulary, where):
    if value is None or isinstance(value, (bool, int, float)):
        return
    if isinstance(value, str):
        for prefix, names in (("cfg.", chain.cfg), ("var.", chain.vars)):
            if value.startswith(prefix):
                if value[len(prefix):] not in names:
                    _fail(f"{where}: unknown {prefix[:-1]} reference {value!r}")
                return
        if value.startswith("clk."):
            _clock(value[4:], vocabulary, where)
        elif value.startswith("obs.") and not value[4:].isidentifier():
            _fail(f"{where}: invalid observation reference {value!r}")
        return  # Other strings are literals, including "k" (antic shorthand).
    if isinstance(value, list):
        for item in value:
            _expr(item, chain, vocabulary, where)
        return
    if not isinstance(value, dict):
        _fail(f"{where}: invalid expression")
    ops = set(value) & {"add", "sub", "min", "max", "fn", "lit"}
    if len(ops) != 1:
        _fail(f"{where}: expression needs one operator; wrap literal objects in lit")
    op = next(iter(ops))
    if op == "fn":
        if not isinstance(value[op], str) or not value[op]:
            _fail(f"{where}: expression function name missing")
        for key, arg in value.items():
            if key != op:
                _expr(arg, chain, vocabulary, where)
        return
    if set(value) != {op}:
        _fail(f"{where}: unexpected expression fields")
    if op == "lit":
        return  # Literal payloads never interpret cfg./var. strings.
    args = value[op]
    if not isinstance(args, list) or (op == "sub" and len(args) != 2) or (op in {"min", "max"} and not args):
        _fail(f"{where}: invalid {op} operands")
    for arg in args:
        _expr(arg, chain, vocabulary, where)


def _guard_args(guard, chain, vocabulary, where):
    if guard is None:
        return
    if "p" in guard:
        for key, value in guard.items():
            if key != "p":
                _expr(value, chain, vocabulary, where)
    elif "not" in guard:
        _guard_args(guard["not"], chain, vocabulary, where)
    else:
        for child in guard.get("all", guard.get("any", [])):
            _guard_args(child, chain, vocabulary, where)


def _mask_spec(spec, vocabulary, where):
    if type(spec) is int and spec >= 0:
        return
    if isinstance(spec, str):
        parts = [p.strip() for p in spec.split("|")]
        if any(not p or p not in MASK_NAMES and p not in vocabulary.directions for p in parts):
            _fail(f"{where}: unknown or empty mask name {spec!r}")
        return
    if not isinstance(spec, dict) or not spec or set(spec) - {"keys", "only", "or"}:
        _fail(f"{where}: invalid mask specification")
    if "keys" in spec and spec["keys"] != "self":
        _fail(f"{where}: mask keys must refer to self")
    if "only" in spec:
        names = spec["only"]
        if spec.get("keys") != "self" or not isinstance(names, list) or any(not isinstance(n, str) or not n for n in names):
            _fail(f"{where}: invalid mask component selection")
        # only is a filter: inherited/variant rules may intentionally match
        # no components on this link (v0 air selects absent hold_jump).
    if "or" in spec:
        if not isinstance(spec["or"], list):
            _fail(f"{where}: mask or needs a list")
        for child in spec["or"]:
            _mask_spec(child, vocabulary, where)
    if "keys" not in spec and "or" not in spec:
        _fail(f"{where}: mask has no keys or operands")


def _rule_syntax(rule, chain, vocabulary, where):
    _guard_args(rule.when, chain, vocabulary, where)
    for changes in (rule.set, rule.pre):
        for name, value in changes.items():
            if name not in chain.vars:
                _fail(f"{where}: assignment to undeclared var {name!r}")
            _expr(value, chain, vocabulary, where)
    if rule.act is not None:
        for name, value in rule.act.items():
            if name != "a":
                _expr(value, chain, vocabulary, where)
    if isinstance(rule.why, dict):
        _expr(rule.why, chain, vocabulary, where)
    if rule.orelse not in (None, "hold") or rule.orelse is not None and rule.do != "try":
        _fail(f"{where}: invalid orelse")
    if rule.emit is not None:
        _mask_spec(rule.emit, vocabulary, where)
    elif rule.mode == "emit":
        _fail(f"{where}: emit mode requires a mask (use 0 for no keys)")


def _link_syntax(link, chain, vocabulary):
    where = link.id
    _clock(link.clock, vocabulary, where)
    _guard_args(link.entry, chain, vocabulary, where)
    for comp in link.keys:
        _clock(comp.clock, vocabulary, where)
        if comp.mask is not None:
            _mask_spec(comp.mask, vocabulary, where)
        if not isinstance(comp.args, dict):
            _fail(f"{where}: generator args must be an object")
        for arg in [comp.lo, comp.hi, *comp.args.values()]:
            _expr(arg, chain, vocabulary, where)
        _guard_args(comp.when, chain, vocabulary, where)
    groups = [link.rules, link.after_keys, link.post, *[chain.rulesets[n] for n in link.inherit]]
    for rules in groups:
        for rule in rules:
            _rule_syntax(rule, chain, vocabulary, where)


def validate_chains(chains: dict[str, Chain], *, vocabulary: ChainVocabulary = DEFAULT_VOCABULARY) -> None:
    """Check references before any anchor/primitive is allowed to execute.

    Primitive names are data, never Python expressions. Resolving their fixed
    vocabulary belongs to the family adapter, not this structural loader.
    """
    if not isinstance(chains, dict) or not chains:
        _fail("table: expected a nonempty chain map")
    for name, chain in chains.items():
        if not isinstance(chain, Chain) or name != chain.id or "." in name or not name:
            _fail(f"{name}: chain identity mismatch")
        _json_finite(chain.to_json(), name)
        if not isinstance(chain.vars, dict) or not isinstance(chain.cfg, dict):
            _fail(f"{name}: vars/cfg must be objects")
        if not chain.links or chain.start not in chain.links:
            _fail(f"{name}: start link missing")
        if not isinstance(chain.admission, dict) or set(chain.admission) != set(chain.links):
            _fail(f"{name}: each link needs its own admission record")
        for lname, link in chain.links.items():
            where = f"{name}.{lname}"
            if not isinstance(link, Link) or not lname or "." in lname or link.id != where:
                _fail(f"{where}: link identity mismatch")
            _guard(link.entry, where)
            for field_name in ("needs", "carry", "inherit"):
                items = getattr(link, field_name)
                if not isinstance(items, list) or any(not isinstance(x, str) or not x for x in items):
                    _fail(f"{where}: invalid {field_name}")
                if len(set(items)) != len(items):
                    _fail(f"{where}: duplicate {field_name}")
            if any(x not in chain.rulesets for x in link.inherit):
                _fail(f"{where}: inherited ruleset missing")
            adm = chain.admission[lname]
            if adm.link != where or adm.status not in ("unfitted", "fitted"):
                _fail(f"{where}: invalid admission identity/status")
            if not isinstance(adm.observations, list) or not isinstance(adm.conditions, list):
                _fail(f"{where}: invalid admission space")
            features = []
            for obs in adm.observations:
                if not isinstance(obs, dict) or not isinstance(obs.get("name"), str) or not obs["name"]:
                    _fail(f"{where}: observation name missing")
                features.append(obs["name"])
            if len(set(features)) != len(features):
                _fail(f"{where}: duplicate observation")
            for cond in adm.conditions:
                if not isinstance(cond, dict) or cond.get("kind") not in ("range", "pred"):
                    _fail(f"{where}: unknown condition")
                if cond["kind"] == "range":
                    if cond.get("obs") not in features or set(cond) - {"kind", "obs", "lo", "hi"}:
                        _fail(f"{where}: invalid range observation/fields")
                    lo, hi = cond.get("lo"), cond.get("hi")
                    if any(x is not None and (isinstance(x, bool) or not isinstance(x, (int, float))) for x in (lo, hi)):
                        _fail(f"{where}: invalid range bounds")
                    if lo is not None and hi is not None and lo > hi:
                        _fail(f"{where}: reversed range")
                elif not isinstance(cond.get("pred"), str) or not cond["pred"] or not isinstance(cond.get("params", {}), dict):
                    _fail(f"{where}: invalid fitted predicate")
            for comp in link.keys:
                if not isinstance(comp, KeyComp) or (comp.mask is None) == (comp.gen is None):
                    _fail(f"{where}: key needs exactly one mask or generator")
                if comp.gen is not None and (not isinstance(comp.gen, str) or not comp.gen):
                    _fail(f"{where}: invalid generator")
                _guard(comp.when, where)
        rule_lists = list(chain.rulesets.values())
        for link in chain.links.values():
            rule_lists.extend((link.rules, link.after_keys, link.post))
        for rules in rule_lists:
            if not isinstance(rules, list):
                _fail(f"{name}: rules must be a list")
            for rule in rules:
                if not isinstance(rule, Rule) or rule.do not in {"set", "act", "keys", "hold", "abort", "done", "goto", "try"}:
                    _fail(f"{name}: unknown rule operation")
                _guard(rule.when, name)
                if rule.mode not in {"same", "keys", "next", "emit"}:
                    _fail(f"{name}: invalid transition mode")
                if not isinstance(rule.set, dict) or not isinstance(rule.pre, dict):
                    _fail(f"{name}: rule variables must be objects")
                if rule.act is not None and (not isinstance(rule.act, dict) or not isinstance(rule.act.get("a"), str)):
                    _fail(f"{name}: invalid action primitive")
                if rule.do in {"goto", "try"}:
                    if not isinstance(rule.to, str) or not rule.to:
                        _fail(f"{name}: transition target missing")
                    target = rule.to.split(".") if "." in rule.to else [name, rule.to]
                    if len(target) != 2 or target[0] not in chains or target[1] not in chains[target[0]].links:
                        _fail(f"{name}: transition target {rule.to!r} missing")
                _rule_syntax(rule, chain, vocabulary, name)
        for link in chain.links.values():
            _link_syntax(link, chain, vocabulary)


def chains_from_json(records: dict, *, vocabulary: ChainVocabulary = DEFAULT_VOCABULARY) -> dict[str, Chain]:
    """Construct and validate v0 records; no file or interpreter side effects."""
    _json_finite(records)
    if not isinstance(records, dict):
        _fail("table: expected chain map")
    try:
        chains = {name: chain_from_json(record) for name, record in records.items()}
        validate_chains(chains, vocabulary=vocabulary)
    except (TypeError, KeyError, AttributeError) as exc:
        raise ChainFormatError(f"invalid v0 record: {exc}") from exc
    return chains


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def load_chains(path, *, vocabulary: ChainVocabulary = DEFAULT_VOCABULARY) -> dict[str, Chain]:
    """Read UTF-8 v0 data; reject duplicate fields instead of silently replacing."""
    from pathlib import Path
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_pairs)
    except json.JSONDecodeError as exc:
        raise ChainFormatError(str(exc)) from exc
    return chains_from_json(raw, vocabulary=vocabulary)


def table_digest(chains: dict[str, Chain], *, vocabulary: ChainVocabulary = DEFAULT_VOCABULARY) -> str:
    import hashlib
    validate_chains(chains, vocabulary=vocabulary)
    data = {name: chain.to_json() for name, chain in chains.items()}
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
