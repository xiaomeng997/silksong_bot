"""Handback ranking AFTER B2 continuation admission, never a second safety gate.

A short-checked N=2 pass survives a modeled tail that cannot reach handback.
Full endpoints below are value projections only, without implied full safety.
Unknown programming exceptions still propagate; only named model unavailability
is recorded per type and skipped.
"""
from __future__ import annotations
import math
from .knife_chain_commitment import ContinuationUnavailable,_unavailable_errors


def handback_value(paths,exits,finish,endpoint,*,unavailable_errors=(ContinuationUnavailable,)):
    """Return (stance_value, evidence) over qualifying continuation TYPES.

    paths is kind -> already short-checked path; finish(kind) lazily supplies that
    same kind's full modeled path; endpoint(path) evaluates the existing stance
    formula. No hit weight, hazard query, admission change or key sending lives
    here. The caller adds its existing hit value after this function.
    """
    unavailable_errors=_unavailable_errors(unavailable_errors)
    if exits.verdict!="pass":raise ValueError("handback ranking requires passed continuation admission")
    kinds=tuple(k for k in paths if k in exits.qualifying_kinds)
    if not kinds or set(kinds)!=set(exits.qualifying_kinds):
        raise ValueError("qualifying continuation paths missing from handback ranking")
    full_values={};full_unavailable=[];short_values={};short_unavailable=[]
    for kind in kinds:
        try:
            full=finish(kind)
            if full.end!="handback":raise ContinuationUnavailable("modeled tail did not hand back")
            value=float(endpoint(full))
            if not math.isfinite(value):raise ContinuationUnavailable("nonfinite modeled handback value")
            full_values[kind]=value
        except unavailable_errors as exc:
            full_unavailable.append({"kind":kind,"type":type(exc).__name__,"reason":str(exc)})
    fallback=not full_values
    if full_values:
        kind=max(full_values,key=full_values.get);value=full_values[kind];mode="best_qualifying_handback"
    else:
        # No finish failure may retroactively invalidate N=2 admission. Reuse
        # only qualified short paths for the explicit approximation.
        for kind in kinds:
            try:
                estimate=float(endpoint(paths[kind]))
                if not math.isfinite(estimate):raise ContinuationUnavailable("nonfinite short endpoint estimate")
                short_values[kind]=estimate
            except unavailable_errors as exc:
                short_unavailable.append({"kind":kind,"type":type(exc).__name__,"reason":str(exc)})
        if short_values:
            kind=max(short_values,key=short_values.get);value=short_values[kind];mode="short_endpoint_fallback"
        else:
            # Explicitly unpriced stance: this is not a claimed zero-risk
            # handback. The accepted admission remains owned by exits.
            kind=None;value=0.;mode="unscored"
    return value,{"mode":mode,"kind":kind,"value_fallback":fallback,"unscored":mode=="unscored",
        "stance_evidence":"none" if mode=="unscored" else "qualified_short_endpoint" if fallback else "modeled_handback",
        "qualifying_kinds":list(kinds),"full_tried":list(kinds),"full_values":full_values,
        "full_unavailable":full_unavailable,"short_values":short_values,
        "short_unavailable":short_unavailable,"all_qualifying_types_max":True,
        "admission_unchanged":True,"admission_mode":exits.mode,
        "scope":"ranking only; full modeled endpoints are not safety/contact certificates"}
