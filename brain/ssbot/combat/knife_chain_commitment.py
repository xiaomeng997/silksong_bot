"""B2 commitment safety policy; not yet wired into the live planner.

The family supplies a nominal path and h2 admission. A geometry adapter supplies
contacts on THAT path, including its queued prefix. This module filters only the
admitted target move through the predicted bounce; later contacts are normal
planner checks. Delayed hazards are always retained, even its own runes.
It neither simulates a path nor grants admission / pogo protection from a future
hit. The continuation threshold is an explicit empirical risk policy, not proof
that the unexamined tails are clear. No ordinary-row horizon is imposed here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


VERDICTS = frozenset({"pass", "reject", "unchecked"})
# Canonical TYPES, not row ids. Close variants of dash_out count only once.
CONTINUATION_KINDS = frozenset({
    "left_landing", "right_landing", "repeat_downslash", "dash_out",
})


def _frame(value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValueError("frame must be a nonnegative integer")


@dataclass(frozen=True)
class MoveInstance:
    target_iid: int
    antic_frame: int
    family: str

    def __post_init__(self):
        if type(self.target_iid) is not int or not self.family:
            raise ValueError("invalid target move identity")
        _frame(self.antic_frame)


@dataclass(frozen=True)
class TargetMoveAdmission:
    """A family guard result, bound to ONE antic and its predicted bounce.

    The adapter must derive move and guard_ref from the h2 guard's same visible
    event, not fill them from a candidate's desired target. This is audit context,
    not a certificate or evidence that a real strike / bounce has happened.
    """
    move: MoveInstance
    decision_frame: int
    bounce_frame: int
    guard_ref: str
    verdict: str

    def __post_init__(self):
        _frame(self.decision_frame)
        _frame(self.bounce_frame)
        if (not self.guard_ref or self.verdict not in VERDICTS
                or self.decision_frame < self.move.antic_frame
                or self.bounce_frame < self.decision_frame):
            raise ValueError("invalid target admission source/window/verdict")


@dataclass(frozen=True)
class PathContact:
    frame: int
    owner_iid: int | None
    kind: str  # body | move | delayed | other
    move: MoveInstance | None = None

    def __post_init__(self):
        _frame(self.frame)
        if self.kind not in {"body", "move", "delayed", "other"}:
            raise ValueError("unknown contact layer")
        if self.move is not None and self.owner_iid != self.move.target_iid:
            raise ValueError("contact owner and move identity differ")


@dataclass(frozen=True)
class ContactScan:
    path_ref: str
    first_frame: int
    last_frame: int
    contacts: tuple[PathContact, ...]
    source: str
    complete: bool = True

    def __post_init__(self):
        _frame(self.first_frame)
        _frame(self.last_frame)
        if self.last_frame < self.first_frame or not self.path_ref or not self.source:
            raise ValueError("invalid contact scan coverage/source")
        if type(self.complete) is not bool:
            raise ValueError("scan completeness must be explicit")
        if not isinstance(self.contacts, tuple):
            raise TypeError("contacts must be an immutable tuple")
        if any(not self.first_frame <= c.frame <= self.last_frame for c in self.contacts):
            raise ValueError("contact outside scan coverage")


@dataclass(frozen=True)
class PathResult:
    verdict: str
    reason: str
    retained: tuple[PathContact, ...] = ()
    trusted_target: tuple[PathContact, ...] = ()


def check_external_path(scan: ContactScan | None, *, path_ref: str,
                        target_move: MoveInstance, first_frame: int,
                        last_frame: int, stage: str,
                        admission: TargetMoveAdmission | None = None) -> PathResult:
    """Check an approach, commitment or continuation with inclusive coverage.

    Approach is a separate uncommitted check refreshed on each actual approach
    tick; it does not borrow a future decision's admission. Continuations are
    normal planner checks too. Only commitment may carry the one-event h2 guard.
    This stage contract does not itself generate/check a path or send any keys.

    Geometry must scan the full path before applying this scope. Do not first
    drop the target iid, its runes, or contacts under a predicted pogo mask.
    Missing geometry / coverage is unchecked. Known retained contacts reject,
    even in an incomplete scan. A later or untagged move is not exempted simply
    because it belongs to the target. Admission is explicit and expires at the
    predicted bounce. Omitting it (all post-bounce continuation checks) exempts
    nothing, including this same move's remaining hammer/body. Actual execution
    must release on an observed bounce, not on this predicted frame alone.
    """
    if stage not in {"approach", "commitment", "continuation"}:
        raise ValueError("unknown chain path stage")
    if stage != "commitment" and admission is not None:
        raise ValueError("only commitment may carry target admission")
    _frame(first_frame)
    _frame(last_frame)
    if not path_ref or last_frame < first_frame:
        raise ValueError("invalid requested path interval")
    if admission is not None:
        if admission.move != target_move:
            raise ValueError("target admission move identity mismatch")
        if admission.decision_frame != first_frame:
            raise ValueError("target admission belongs to another decision frame")
    if scan is None:
        return PathResult("unchecked", "contact scan missing")
    if scan.path_ref != path_ref:
        return PathResult("unchecked", "scan belongs to another path")
    retained, trusted = [], []
    for c in scan.contacts:
        if not first_frame <= c.frame <= last_frame:
            continue
        exempt = (admission is not None and admission.verdict == "pass"
                  and c.frame <= admission.bounce_frame
                  and c.kind in {"body", "move"} and c.move == admission.move)
        dest = trusted if exempt else retained
        dest.append(c)
    if retained:
        return PathResult("reject", "planner-checked contact (target outside scope / other / delayed / unknown)",
                          tuple(retained), tuple(trusted))
    if not scan.complete or scan.first_frame > first_frame or scan.last_frame < last_frame:
        return PathResult("unchecked", "path coverage incomplete", (), tuple(trusted))
    if stage == "commitment" and admission is None:
        return PathResult("unchecked", "commitment target admission missing")
    if admission is not None and admission.verdict != "pass":
        return PathResult(admission.verdict, "target family admission did not pass")
    return PathResult("pass", "checked path clear; any target exemption is bounded by admission",
                      (), tuple(trusted))


@dataclass(frozen=True)
class Continuation:
    option_id: str
    kind: str
    bounce_state_ref: str
    path_ref: str
    handback_frame: int
    first_executable: bool | None
    admission: str
    short_scan: ContactScan | None

    def __post_init__(self):
        if (not self.option_id or self.kind not in CONTINUATION_KINDS
                or not self.bounce_state_ref or not self.path_ref):
            raise ValueError("invalid continuation identity/kind")
        _frame(self.handback_frame)
        if self.first_executable is not None and type(self.first_executable) is not bool:
            raise ValueError("first executable must be bool or unknown")
        if self.admission not in VERDICTS:
            raise ValueError("invalid continuation admission")


@dataclass(frozen=True)
class ContinuationCheck:
    option_id: str
    kind: str
    stage: str  # entry | short | full
    verdict: str
    reason: str
    path_result: PathResult | None = None


@dataclass(frozen=True)
class ContinuationResult:
    verdict: str
    mode: str  # lower_bound | full_exit | none | unchecked
    qualifying_kinds: tuple[str, ...]
    full_checked: tuple[str, ...]
    unknown_options: tuple[str, ...]
    reason: str
    checks: tuple[ContinuationCheck, ...]


def assess_continuations(options: tuple[Continuation, ...], *, target_move: MoveInstance,
                         bounce_state_ref: str, bounce_frame: int, short_frames: int,
                         full_scan: Callable[[Continuation], ContactScan | None],
                         minimum_kinds: int = 2) -> ContinuationResult:
    """Apply the user's N=2 lower bound at ONE predicted bounce state.

    Each admitted executable type gets a NORMAL short planner check, including
    the target's current/next moves and body. Pre-bounce admission is never passed
    to either short or full scans here. At >=N
    types no complete exit is queried. Below N, fully check the surviving options
    until one reaches handback. No usable option => do not jump. Unknowns never
    count; rejection with unknown options remains unchecked. Repeated downslash
    needs its own admission, including when its link has not been encoded yet.

    short_frames is explicit: its empirical calibration belongs to the caller,
    not a hidden 36-frame or new arbitrary constant in this policy.
    """
    _frame(bounce_frame)
    if (type(short_frames) is not int or short_frames < 1
            or type(minimum_kinds) is not int or minimum_kinds < 1
            or not bounce_state_ref):
        raise ValueError("invalid continuation threshold/state/short horizon")
    if len({o.option_id for o in options}) != len(options):
        raise ValueError("duplicate continuation option")
    if any(o.bounce_state_ref != bounce_state_ref for o in options):
        raise ValueError("cannot combine continuations from different bounce states")
    if any(o.handback_frame < bounce_frame for o in options):
        raise ValueError("handback precedes bounce")
    eligible, unknown, checks = [], [], []
    for o in options:
        if o.first_executable is False or o.admission == "reject":
            checks.append(ContinuationCheck(o.option_id, o.kind, "entry", "reject",
                                            "first action unavailable or own admission rejected"))
            continue
        if o.first_executable is None or o.admission == "unchecked":
            unknown.append(o.option_id)
            checks.append(ContinuationCheck(o.option_id, o.kind, "entry", "unchecked",
                                            "first action or own admission unknown"))
            continue
        short = check_external_path(
            o.short_scan, path_ref=o.path_ref, target_move=target_move,
            first_frame=bounce_frame,
            last_frame=min(o.handback_frame, bounce_frame + short_frames),
            stage="continuation")
        checks.append(ContinuationCheck(o.option_id, o.kind, "short", short.verdict,
                                        short.reason, short))
        if short.verdict == "pass":
            eligible.append(o)
        elif short.verdict == "unchecked":
            unknown.append(o.option_id)
    kinds = tuple(sorted({o.kind for o in eligible}))
    if len(kinds) >= minimum_kinds:
        return ContinuationResult("pass", "lower_bound", kinds, (), tuple(unknown),
                                  "short-checked type threshold; full tails unexamined",
                                  tuple(checks))
    checked = []
    for o in eligible:
        checked.append(o.option_id)
        result = check_external_path(
            full_scan(o), path_ref=o.path_ref, target_move=target_move,
            first_frame=bounce_frame, last_frame=o.handback_frame, stage="continuation")
        checks.append(ContinuationCheck(o.option_id, o.kind, "full", result.verdict,
                                        result.reason, result))
        if result.verdict == "pass":
            return ContinuationResult("pass", "full_exit", kinds, tuple(checked),
                                      tuple(unknown), "one surviving exit clear to handback",
                                      tuple(checks))
        if result.verdict == "unchecked" and o.option_id not in unknown:
            unknown.append(o.option_id)
    return ContinuationResult(
        "unchecked" if unknown else "reject", "unchecked" if unknown else "none",
        kinds, tuple(checked), tuple(unknown),
        "no verified continuation; do not jump", tuple(checks))
