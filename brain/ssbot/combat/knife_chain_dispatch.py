"""Candidate/selection/send/observation boundary for the synchronous controller.

This ledger never owns the keyboard and never advances a chain Run. The native
adapter must derive its next actual context from these receipts and observed
history, not from a preview of an unselected link. Transport send != game accept.
"""
from __future__ import annotations

from dataclasses import dataclass

from .knife_chain_admission import AdmissionDecision
from .knife_chain_format import SEND_AHEAD


@dataclass(frozen=True)
class Offer:
    serial: int
    frame: int
    target_frame: int
    link: str
    desired_mask: int
    table_ref: str
    admission: AdmissionDecision

    @property
    def owner(self):
        return "knife_chain:" + self.link


@dataclass(frozen=True)
class Selection:
    offer: Offer
    mode: str  # fitted | probe; a probe is never relabelled a fitted admission
    probe_ref: str | None


@dataclass(frozen=True)
class SentAction:
    frame: int
    target_frame: int
    desired_mask: int
    wire_mask: int | None  # None until Hold/filter outcome is known
    owner: str
    selection: Selection | None
    chain_outcome: str  # sent | overridden | unselected


@dataclass(frozen=True)
class LatchedAction:
    sent: SentAction
    observed_frame: int
    mask: int
    outcome: str  # match | differs | wire_unchecked


def _mask(value):
    if type(value) is not int or value < 0:
        raise ValueError("mask must be a nonnegative integer")


class ChainDispatch:
    """One episode's causal action ledger; no controller or world simulation.

    offer() accepts a pure preview's output; it does not store a speculative Run.
    select() records ranking only. record_send() is called after a successful
    transport send, with the FINAL owner/mask after all supervisors. observe()
    records a subsequent STATE's act target/mask (and can report disagreement).
    Explicit experiment scope is retained as probe_ref for unfitted/out-of-region
    proposals; this class does not itself authorize or launch any experiment.
    """

    def __init__(self):
        self.frame: int | None = None
        self._serial = 0
        self._offers: dict[int, Offer] = {}
        self.selection: Selection | None = None
        self._sent: dict[int, SentAction] = {}
        self._latched: dict[int, LatchedAction] = {}

    def reset(self) -> None:
        """Call at episode start; invalidate offers and clear action/latch history.

        Frame numbers may restart in the next episode. Serials remain monotonic
        and select() still checks object identity, so old offers cannot re-enter.
        """
        self.frame = None
        self._offers.clear()
        self.selection = None
        self._sent.clear()
        self._latched.clear()

    def begin_tick(self, frame: int) -> None:
        if type(frame) is not int or (self.frame is not None and frame <= self.frame):
            raise ValueError("decision frames must increase")
        self.frame = frame
        self._offers.clear()
        self.selection = None

    def offer(self, link: str, desired_mask: int, *, table_ref: str,
              admission: AdmissionDecision) -> Offer:
        _mask(desired_mask)
        if self.frame is None or admission.frame != self.frame or admission.link != link:
            raise ValueError("offer admission belongs to another tick/link")
        if admission.verdict not in {"pass", "reject", "unchecked"} or not table_ref:
            raise ValueError("invalid offer evidence")
        self._serial += 1
        offer = Offer(self._serial, self.frame, self.frame + SEND_AHEAD, link,
                      desired_mask, table_ref, admission)
        self._offers[offer.serial] = offer
        return offer

    def select(self, offer: Offer, *, probe_ref: str | None = None) -> Selection:
        if self._offers.get(offer.serial) is not offer or offer.frame != self.frame:
            raise ValueError("offer is stale or belongs to another dispatch")
        if self.selection is not None:
            raise ValueError("tick already selected; overrides belong to final send")
        if offer.admission.verdict != "pass" and not probe_ref:
            raise ValueError("unfitted/rejected offer requires an explicit probe scope")
        mode = "probe" if probe_ref else "fitted"
        self.selection = Selection(offer, mode, probe_ref)
        return self.selection

    def record_send(self, *, frame: int, target_frame: int, desired_mask: int,
                    wire_mask: int | None, owner: str) -> SentAction:
        """Receipt of an actual successful send, including ordinary/supervisor keys.

        A transport failure must not call this method. This records audit facts;
        it must not be used as a receipt before the real sender was called.
        """
        _mask(desired_mask)
        if wire_mask is not None:
            _mask(wire_mask)
        if frame != self.frame or target_frame != frame + SEND_AHEAD or not owner:
            raise ValueError("send does not match this decision tick")
        if target_frame in self._sent:
            raise ValueError("cannot replace an action already sent")
        selection = self.selection
        outcome = "unselected"
        if selection is not None:
            offer = selection.offer
            outcome = "sent" if owner == offer.owner and desired_mask == offer.desired_mask else "overridden"
        elif owner.startswith("knife_chain:"):
            raise ValueError("chain send without a selection")
        sent = SentAction(frame, target_frame, desired_mask, wire_mask, owner, selection, outcome)
        self._sent[target_frame] = sent
        return sent

    def queued(self, *, after: int) -> tuple[SentAction, ...]:
        """Known in-flight actions, retaining desired/wire distinction and unknowns."""
        return tuple(self._sent[f] for f in sorted(self._sent) if f > after)

    def observe(self, *, observed_frame: int, target_frame: int, mask: int) -> LatchedAction:
        _mask(mask)
        if observed_frame < target_frame or target_frame not in self._sent:
            raise ValueError("no causal send for this observed target")
        sent = self._sent[target_frame]
        outcome = "wire_unchecked" if sent.wire_mask is None else "match" if mask == sent.wire_mask else "differs"
        latched = LatchedAction(sent, observed_frame, mask, outcome)
        previous = self._latched.get(target_frame)
        if previous is not None:
            if previous.mask != mask:
                raise ValueError("conflicting latch for the same action")
            return previous
        self._latched[target_frame] = latched
        return latched
