"""Opt-in audit bridge at the old controller's real selection/send boundaries.

No generator, interpreter, rank override or executor. Observations distinguish
requested keys, transport success, oracle application and HoldFilter latch; none
of these alone proves a hero move or planned strike was accepted. Trace storage
is bounded and explicitly reports eviction; it is not a complete live-run audit.
"""
from __future__ import annotations

from collections import Counter, deque
from copy import deepcopy
import time

from .knife_chain_dispatch import ChainDispatch


class NativeChainAuditError(RuntimeError):
    """Native bridge integrity failure; the episode harness records HARNESS_FAIL."""


class NativeChainAudit:
    def __init__(self, trace_limit=2048):
        self.dispatch = ChainDispatch()
        self.trace_limit = trace_limit
        self.reset(-1)

    def reset(self, episode, *, start_frame=None):
        self.dispatch.reset()
        self.episode = episode
        self.counts = Counter()
        self.events = deque(maxlen=self.trace_limit)
        self.trace_evicted = 0
        self.last_observed = start_frame
        self._rows = {}
        self._final = None
        self.planner_context = None
        self._observed_targets = set()
        self._prepared = None

    def _note(self, event, **data):
        self.counts[event] += 1
        if len(self.events) == self.events.maxlen:
            self.trace_evicted += 1
        self.events.append({"event": event, "episode": self.episode, **data})

    def begin(self, state, history=()):
        frame = state["f"]
        # Inbox snapshots can include newer frames received while planning; they
        # must never enter this tick's observed context.
        # Without an episode fence, the first decision may not import old inbox
        # entries. With a fence, retain every available intervening STATE.
        pending = {} if self.last_observed is None else {
            s["f"]: s for s in history if self.last_observed < s.get("f", frame + 1) <= frame}
        pending[frame] = state
        for f in sorted(pending):
            if self.last_observed is None or f > self.last_observed:
                self.observe(pending[f])
        try:
            self.dispatch.begin_tick(frame)
        except ValueError as exc:
            raise NativeChainAuditError(str(exc)) from exc
        self._rows.clear()
        self._final = self._prepared = None
        self.planner_context = None
        self._note("decision_begin", frame=frame)

    def observe(self, state):
        f = state["f"]
        if self.last_observed is not None:
            if f <= self.last_observed:
                return
            if f > self.last_observed + 1:
                self._note("state_gap", first=self.last_observed + 1, last=f - 1)
        self.last_observed = f
        act = deepcopy(state.get("act") or {})
        self._note("state_sample", frame=f, act=act)
        target, applied, mask = (act.get(n) for n in ("target", "applied", "mask"))
        if not all(type(n) is int for n in (target, applied, mask)) or mask < 0:
            self._note("action_unknown", frame=f, reason="missing action fields")
            return
        sent = self.dispatch.sent_for(target)
        if sent is None:
            self._note("action_untracked", frame=f, target=target)
            return
        if not target <= applied <= f:
            self._note("action_unknown", frame=f, target=target, reason="inconsistent application frame")
            return
        desired = (act.get("hf") or {}).get("desired")
        desired_agrees = desired == sent.desired_mask if type(desired) is int else None
        self._note("application_sample", frame=f, target=target, applied=applied,
                   exact_application_frame=applied == f, desired_agrees=desired_agrees,
                   latched_mask=mask)
        # A held key may change on later frames of this same action. Preserve
        # each sample above; the ledger's one receipt must not invent a conflict.
        if target not in self._observed_targets:
            self.dispatch.observe(observed_frame=f, target_frame=target, mask=mask)
            self._observed_targets.add(target)
            self._note("application_first_seen", frame=f, target=target, applied=applied,
                       exact_application_frame=applied == f, wire_status="unchecked")

    def planner_input(self, *, origin, prefix, hold, hero_state):
        """Freeze native model inputs and distinguish intended prefix from receipts.

        Hold is the planner's state at origin, not a prediction that a sent action
        was latched. Missing receipts and unknown future wire masks stay unknown.
        """
        f = self.dispatch.frame
        if f is None or origin > f or len(prefix) != f - origin + 1:
            raise NativeChainAuditError("planner prefix does not match origin/decision frames")
        def data(value):
            return deepcopy(value.tolist() if hasattr(value, "tolist") else value)
        receipt_prefix = []
        for target, wanted in zip(range(origin + 1, f + 2), prefix):
            sent = self.dispatch.sent_for(target)
            receipt_prefix.append({"target": target, "planner_desired": int(wanted),
                "transport_desired": None if sent is None else sent.desired_mask,
                "wire": None if sent is None else sent.wire_mask})
        self.planner_context = {"frame": f, "origin": origin, "prefix": receipt_prefix,
            "hold": {name: data(getattr(hold, name)) for name in ("latched", "desired", "pending", "age")},
            "hero_state": data(hero_state)}
        self._note("planner_input", **deepcopy(self.planner_context))

    def register_row(self, index, offer, *, probe_ref=None):
        """Future producer hook; records a row identity, never injects a row/key."""
        if type(index) is not int or index < 0 or index in self._rows:
            raise NativeChainAuditError("row index must be nonnegative and unique this tick")
        if offer.frame != self.dispatch.frame:
            raise NativeChainAuditError("row offer belongs to another decision")
        self._rows[index] = (offer, probe_ref)
        self._note("row_registered", frame=offer.frame, row=index, link=offer.link)

    def planner_result(self, result, *, fresh=True):
        index, mask = int(result.idx), int(result.mask)
        self._note("planner_selected", frame=self.dispatch.frame, row=index, mask=mask,
                   name=str(result.name), fresh=bool(fresh))
        if index not in self._rows:
            return
        offer, probe_ref = self._rows[index]
        if not fresh or mask != offer.desired_mask:
            self._note("row_identity_reject", frame=self.dispatch.frame, row=index,
                       reason="cached result" if not fresh else "mask differs")
            return
        try:
            self.dispatch.select(offer, probe_ref=probe_ref)
        except ValueError as exc:
            self._note("row_contract_error", frame=self.dispatch.frame, row=index, reason=str(exc))
            raise NativeChainAuditError(str(exc)) from exc
        self._note("chain_selected", frame=self.dispatch.frame, row=index, link=offer.link)

    def final(self, owner, mask):
        # Called before the measurement-only early return, including supervisor,
        # pause, real-quit and missing-world-state paths.
        self._final = (str(owner), int(mask))
        self._note("policy_final", frame=self.dispatch.frame, owner=str(owner), mask=int(mask))

    def before_send(self, *, frame, target, mask, flags, received_frame):
        """Validate BEFORE the sender; selection/policy return are not receipts."""
        if frame != self.dispatch.frame or target != frame + 2:
            raise NativeChainAuditError("native send does not match the decision frame")
        if self.dispatch.sent_for(target) is not None:
            raise NativeChainAuditError("target already sent")
        final = self._final
        if final is not None and final[1] != int(mask):
            raise NativeChainAuditError("returned mask differs from final policy mask")
        owner = final[0] if final is not None else "unknown"
        selection = self.dispatch.selection
        if selection is not None and owner == "plan" and int(mask) == selection.offer.desired_mask:
            owner = selection.offer.owner
        self._prepared = {"frame": frame, "target": target, "mask": int(mask), "flags": int(flags),
                          "owner": owner, "received_frame_before_send": received_frame}
        self._note("send_prepared", **self._prepared)

    def send_failed(self, error):
        self._note("transport_failed", frame=self.dispatch.frame, error=error)
        self._prepared = None

    def sent(self):
        """Only episode._act after link.act returns successfully may call this."""
        if self._prepared is None:
            raise NativeChainAuditError("send receipt without a prepared action")
        data, self._prepared = self._prepared, None
        sent = self.dispatch.record_send(frame=data["frame"], target_frame=data["target"],
                    desired_mask=data["mask"], wire_mask=None, owner=data["owner"])
        self._note("transport_sent", **data, chain_outcome=sent.chain_outcome,
                   send_return_ns=time.perf_counter_ns())
        return sent

    def summary(self):
        return {"episode": self.episode, "mode": "audit_only", "counts": dict(self.counts),
                "trace": list(self.events), "trace_evicted": self.trace_evicted,
                "buffer_complete": self.trace_evicted == 0, "last_observed_frame": self.last_observed,
                "observation_gaps": self.counts["state_gap"], "send_scope": "episode._act_only",
                "last_planner_context": deepcopy(self.planner_context),
                "candidate_generation": False, "wire_prediction": "unchecked"}
