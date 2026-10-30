"""Evaluate fitted link conditions on causal observations, outside the interpreter.

A pass means inside the supplied empirical region, not a safety certificate.
Unfitted records can still be replayed or sampled under a named probe protocol.
No strict-world, H/contact or common-exit gate is introduced here.
"""
from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable, Mapping

from .knife_chain_format import Admission, ChainFormatError


@dataclass(frozen=True)
class Observation:
    value: object
    available_at: int
    source: str


@dataclass(frozen=True)
class ConditionResult:
    name: str
    verdict: str  # pass | reject | unchecked
    reason: str


@dataclass(frozen=True)
class AdmissionDecision:
    link: str
    verdict: str
    frame: int
    fit_ref: str | None
    checks: tuple[ConditionResult, ...]


def evaluate_admission(admission: Admission, observations: Mapping[str, Observation], *, frame: int,
                       fit_ref: str | None = None, predicates: Mapping[str, Callable] | None = None,
                       cutoffs: Mapping[str, int] | None = None) -> AdmissionDecision:
    """Evaluate a conjunction of active ranges and correlated predicates.

    None bounds / unfitted predicates are inactive templates, not restrictions.
    A fitted space needs at least one active condition and a versioned fit_ref.
    Predicate params may declare `observations`; otherwise all declared features
    are inputs. Predicates receive (values, params, fitted), returning bool/None.

    Availability defaults to the current decision frame. A branch needing the
    two-frame observation lead supplies its own feature cutoffs (frame - 2);
    current ground/input features are not universally delayed by two frames.
    """
    predicates, cutoffs = predicates or {}, cutoffs or {}
    if admission.status not in ("unfitted", "fitted"):
        raise ChainFormatError("unknown admission status")
    declared = {o["name"] for o in admission.observations}
    if not set(cutoffs) <= declared:
        raise ValueError("cutoff uses undeclared observation names")
    if any(type(c) is not int or c > frame for c in cutoffs.values()):
        raise ValueError("observation cutoff must not be in the future")
    if admission.status == "unfitted" or not fit_ref:
        reason = "unfitted" if admission.status == "unfitted" else "fit reference missing"
        return AdmissionDecision(admission.link, "unchecked", frame, fit_ref,
                                 (ConditionResult("space", "unchecked", reason),))
    checks = []

    def inputs(names):
        if not set(names) <= declared:
            raise ChainFormatError("predicate uses undeclared observations")
        values = {}
        for name in names:
            obs = observations.get(name)
            if obs is None or not obs.source or obs.value is None:
                return None, f"{name}: unavailable"
            if type(obs.available_at) is not int or obs.available_at > cutoffs.get(name, frame):
                return None, f"{name}: after information cutoff"
            values[name] = obs.value
        return values, ""

    for condition in admission.conditions:
        kind = condition["kind"]
        if kind == "range":
            lo, hi = condition.get("lo"), condition.get("hi")
            if lo is None and hi is None:
                continue
            name = condition["obs"]
            vals, why = inputs([name])
            if vals is None:
                checks.append(ConditionResult(name, "unchecked", why))
                continue
            value = vals[name]
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                checks.append(ConditionResult(name, "unchecked", "not a finite numeric/bool observation"))
            else:
                ok = (lo is None or value >= lo) and (hi is None or value <= hi)
                checks.append(ConditionResult(name, "pass" if ok else "reject", "in range" if ok else "outside range"))
        elif kind == "pred":
            if condition.get("fitted") is None:
                continue
            name, params = condition["pred"], condition.get("params", {})
            names = params.get("observations", sorted(declared))
            if not isinstance(names, list) or any(not isinstance(n, str) for n in names):
                raise ChainFormatError("invalid predicate observation list")
            vals, why = inputs(names)
            fn = predicates.get(name)
            if vals is None or fn is None:
                checks.append(ConditionResult(name, "unchecked", why or "predicate not registered"))
                continue
            # Unexpected predicate exceptions are defects, not low coverage.
            answer = fn(deepcopy(vals), deepcopy(params), deepcopy(condition["fitted"]))
            if answer is not None and type(answer) is not bool:
                raise TypeError(f"{name}: predicate must return bool or None")
            verdict = "unchecked" if answer is None else "pass" if answer else "reject"
            checks.append(ConditionResult(name, verdict, "predicate result"))
        else:
            raise ChainFormatError(f"unknown condition {kind}")
    if not checks:
        checks.append(ConditionResult("space", "unchecked", "no fitted conditions"))
    verdict = "reject" if any(c.verdict == "reject" for c in checks) else (
        "unchecked" if any(c.verdict == "unchecked" for c in checks) else "pass")
    return AdmissionDecision(admission.link, verdict, frame, fit_ref, tuple(checks))
