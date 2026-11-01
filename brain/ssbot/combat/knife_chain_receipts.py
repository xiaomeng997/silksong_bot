"""The user's Opt1 key-application receipts: one criterion for B2 and the non-candidate strict audit.

Opt1ReceiptMixin._observe_application is NativeChainB2._observe_application moved verbatim (knife_chain_b2.py at
1fa88736, :226-273). A matching report late by <= 2 frames resolves its target; a later matching report covers the
skipped targets before it (same key or a key change); a target with neither through T+4 stops on T+5; a reported
desired that differs from the successful send stops. Coverage is not an exact application or an accepted action.
A class using the mixin owns _receipts, _pending, _application, _late_bound_targets and _last_matching_report and
provides _note, _receipt_note and _stop.

StrictReceiptAudit is the thin non-candidate audit for runs without B2 (SSBOT_FORUM_CHAIN_STRICT_RECEIPTS=1 with
CHAIN_NATIVE=0): NativeChainAudit's real begin / before_send / sent boundaries plus this stop. It proposes no rows
and owns no keys. Every successful send is a receipt; one sent without ACTION_EXCLUSIVE (ordinary play keys) is also
pending, so the four-frame bound applies to it. The pause machine's and the real quit's EXCLUSIVE keys are receipts
only (their reports still cover earlier targets and are checked for a desired mismatch, as in B2); their menu-time
reports have not been verified live.
"""
from __future__ import annotations

from collections import Counter

from ssbot.ipc.framing import ACTION_EXCLUSIVE

from .knife_chain_native import NativeChainAudit, NativeChainAuditError


class Opt1ReceiptMixin:
    def _observe_application(self,state):
        f=state["f"];act=state.get("act") or {}
        target=act.get("target");applied=act.get("applied");desired=(act.get("hf") or {}).get("desired")
        sent=self._receipts.get(target)
        valid=False
        if sent is not None and type(desired) is int:
            if desired!=sent:
                self._receipt_note("desired_mismatch",f,target=target,wanted=sent,reported_desired=desired)
                self._stop("key application desync: desired differs from successful send",f)
            valid=type(applied) is int and target<=applied<=min(f,target+2)
            if target in self._pending and type(applied) is int and applied>target+2:
                if applied<=f:self._late_bound_targets.add(target)
                self._note("b2_application_outside_late_bound",frame=f,target=target,applied=applied,
                           accepted="unchecked; await later matching report")
        if valid:
            previous=self._last_matching_report
            for t,wanted in sorted(tuple(self._pending.items())):
                direct=t==target
                covered=previous is not None and previous["target"]<t<target
                if (not direct and not covered) or f>t+4:continue
                if direct and wanted!=desired:self._stop("key application desync",f)
                self._pending.pop(t)
                same=covered and wanted==desired  # skipped target vs its covering later report
                late_beyond=covered and t in self._late_bound_targets
                proof={"target":t,"observed":f,"desired":wanted,"reported_target":target,
                       "kind":"direct" if direct else "covered_late_beyond_bound" if late_beyond else "covered_same_key" if same else "covered_changed_key",
                       "applied":applied if direct else None,
                       "between":None if direct else [previous["target"],target]}
                self._application[t]=proof
                self._receipt_note("late_beyond_bound" if late_beyond else "skip_same_key" if same else "skip_key_change" if covered else "lag" if applied>t else "direct",
                    f,target=t,reported_target=target,desired=wanted,lag=applied-t if direct else None,
                    between=proof["between"],hero_action="unchecked",contact="unchecked")
                self._note("chain_application_observed",frame=f,**proof,hero_action="unchecked",contact="unchecked")
                if late_beyond:
                    self._note("b2_application_late_beyond_bound_covered",frame=f,**proof)
                elif covered:
                    self._note("b2_application_skipped",frame=f,**proof)
                    self._note("b2_application_skipped_same_key" if same else "b2_application_skipped_changed_key",frame=f,**proof)
                elif applied>t:self._note("b2_application_late",frame=f,delay=applied-t,**proof)
            if previous is None or target>previous["target"]:
                self._last_matching_report={"target":target,"desired":desired,"observed":f}
        # User opt1: valid reports bracket skipped targets, even across key
        # changes. Coverage is not an exact application or accepted-action claim.
        # Allow through T+4; on T+5 without any proof, stop.
        overdue=[t for t in self._pending if t<f-4]
        if overdue:
            for t in overdue:self._receipt_note("uncovered_timeout",f,target=t,desired=self._pending[t],upper_bound=t+4)
            self._stop("missing critical application receipt beyond four-frame upper bound",f)


class StrictReceiptStop(NativeChainAuditError):
    """Opt1 stop of the strict audit; out of policy.act the episode harness records HARNESS_FAIL."""


class StrictReceiptAudit(Opt1ReceiptMixin, NativeChainAudit):
    strict_receipts = True

    def reset(self, episode, *, start_frame=None):
        super().reset(episode, start_frame=start_frame)
        self._receipts = {}
        self._pending = {}
        self._application = {}
        self._late_bound_targets = set()
        self._last_matching_report = None
        self._receipt_counts = Counter()
        self.strict_stop = None

    def _note(self, event, **data):
        # One criterion, two owners: the shared body's b2_* events carry this audit's prefix.
        if event.startswith("b2_"):
            event = "strict_" + event[3:]
        return super()._note(event, **data)

    def _receipt_note(self, kind, frame, **data):
        self._receipt_counts[kind] += 1
        self._note("strict_receipt", frame=frame, kind=kind, **data,
                   scope="every successful send; not hero action acceptance")

    def _stop(self, reason, frame=None):
        frame = self.last_observed if frame is None else frame
        self.strict_stop = str(reason)
        self._note("strict_receipt_stop", frame=frame, reason=str(reason))
        raise StrictReceiptStop(str(reason))

    def observe(self, state):
        f = state["f"]
        if self.last_observed is not None and f <= self.last_observed:
            return
        super().observe(state)
        self._observe_application(state)

    def sent(self):
        flags = int((self._prepared or {}).get("flags", 0) or 0)
        sent = super().sent()
        self._receipts[sent.target_frame] = sent.desired_mask
        for old in [t for t in self._receipts if t < sent.frame - 1202]:
            del self._receipts[old]
        if not flags & ACTION_EXCLUSIVE:
            self._pending[sent.target_frame] = sent.desired_mask
        return sent

    def summary(self):
        return {**super().summary(), "mode": "strict_receipt_audit", "strict_receipts": True,
                "receipt_counts": dict(self._receipt_counts), "pending_application": sorted(self._pending),
                "strict_stop": self.strict_stop,
                "receipt_scope": "Opt1 on every successful non-EXCLUSIVE send; EXCLUSIVE keys are receipts only"}
