"""Menu key guard (DESIGN §3.7.5 step 2, §3.8.2 "no game key may leak into a visible menu: Z = Submit, X / A = Cancel",
m0:N16): the pause loop's first Pause press waits until no other key can still be latched on the frame it reaches the
game, so the pause menu never opens over a held or replayed game key.

Why a guard is needed. Every key path (the oracle's HoldFilter, oracle/src/Input/HoldFilter.cs; the final inputd
sink, which enforces the same C19 limits) keeps each requested edge and replays it with the minimum press / release
(2 / 2 frames): a key pressed on frame p cannot be released before p + 2, and a press the filter deferred for the
minimum release fires later even when the caller has stopped asking for it. When the supervisor raises PAUSE_PENDING
while the planner holds keys, the planner's last ACTIONs are still in flight (training: the ACTION for frame f + 1 was
sent at f - 1), so a Pause press sent at f for f + 2 can land together with a planner key latched on the pause frame,
or followed by a replayed press inside the menu. pause_stress (11b4ca0 docstring) found a movement key latched 1-2
frames into the pause in 9 of the 37 gate / live QUITs (20261002_123347 ... 152649) and newly pressed on the pause
frame in 4; the 112 injected-hit pauses of 20261002_180411 had none only because a hit closes the pause gate for
15 frames, long enough for the filter to drain.

The rule. A Pause press may start only when, replaying the filter from its exported state (STATE act.hf after the
observed frame) through the ACTIONs sent but not applied yet, no key outside `allowed` (the Pause key) is latched on
the frame the press lands and none has an edge still queued (nothing can fire later); the caller sends no game keys
from the trigger on (the pause machine's mask replaces the planner's), so the latched keys drain within the minimum
press. The in-flight ACTIONs are those for the frames after the last one the oracle applied (STATE act.target) up to
the press's own: training sends the mask for f + 2 at STATE f, so normally just the one for f + 1, but an ACTION that
missed its frame (a slow brain tick) is still pending at the next STATE and is applied with the next one in arrival
order; leaving it out let a planner press reach the pause frame in 56 of 2000 simulated trials
(tests/test_key_guard.py). Checked for every way the in-flight ones can land (one per frame, all in the next update,
all with the press). Cost: 0 frames when no game key is down, at most the minimum press (2 frames) otherwise.

    inflight = [sent[g] for g in range(s["act"]["target"] + 1, f + 2)]
    clear = keys_clear(s["act"]["hf"], inflight, press=1 << BIT["pause"])   # None: no act.hf

A second layer sits in the oracle (built 2026-10-02, not yet deployed): the ACTION EXCLUSIVE flag
(framing.ACTION_EXCLUSIVE, HoldFilter.Exclusive), which the pause machine's ACTIONs carry, releases every other key on
its frame below the minimum press and drops their queued edges, so the press could go out without waiting; the guard
still models the plain filter (an oracle without the flag, or a sink that does not implement it, stays safe).

Filter is a scalar mirror of HoldFilter.cs (Push / Step / Exclusive, left-right exclusion, the pending-toggle cap);
tests/test_key_guard.py checks it frame for frame against ssbot.knowledge.kinematics.hold_filter on random streams.
Pure Python, no numpy: the final-run inputd can use it as is.
"""
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

N_BITS = 22                      # ACTION button bits (ssbot.ipc.framing.BUTTONS)
LEFT_BIT, RIGHT_BIT = 20, 21
AGE_LONG = 1 << 20
MAX_PENDING_TOGGLES = 3


@dataclass(slots=True)
class Filter:
    """oracle/src/Input/HoldFilter.cs on int masks."""
    latched: int = 0
    desired: int = 0
    pending: list[int] = field(default_factory=lambda: [0] * N_BITS)
    age: list[int] = field(default_factory=lambda: [AGE_LONG] * N_BITS)
    min_press: int = 2
    min_release: int = 2

    @classmethod
    def from_hf(cls, hf: Mapping, min_press: int = 2, min_release: int = 2) -> "Filter":
        """From STATE act.hf {latched, desired, pending [22], age [22] (capped at 255 in the export: the filter only
        compares ages with the 2-frame limits)}."""
        def ints(v, default: int) -> list[int]:
            out = [default] * N_BITS
            for i, x in enumerate(list(v or ())[:N_BITS]):
                out[i] = int(x)
            return out
        return cls(int(hf.get("latched") or 0), int(hf.get("desired") or 0), ints(hf.get("pending"), 0),
                   ints(hf.get("age"), AGE_LONG), min_press, min_release)

    def copy(self) -> "Filter":
        return Filter(self.latched, self.desired, list(self.pending), list(self.age), self.min_press,
                      self.min_release)

    def push(self, want: int) -> None:
        changed = want ^ self.desired
        if not changed:
            return
        self.desired = want
        for i in range(N_BITS):
            if changed >> i & 1:
                self.pending[i] += 1
                if self.pending[i] > MAX_PENDING_TOGGLES:
                    self.pending[i] -= 2

    def step(self, want: int) -> int:
        """One latched frame: the wanted set in, the set the game sees out."""
        self.push(want)
        nxt, pressed = self.latched, 0
        for i in range(N_BITS):
            if not self.pending[i]:
                continue
            b = 1 << i
            if self.latched & b:
                if self.age[i] >= self.min_press:
                    nxt &= ~b
                    self.pending[i] -= 1
            elif self.age[i] >= self.min_release:
                nxt |= b
                pressed |= b
                self.pending[i] -= 1
        lb, rb = 1 << LEFT_BIT, 1 << RIGHT_BIT
        if nxt & lb and nxt & rb:
            for i in (LEFT_BIT, RIGHT_BIT):
                b = 1 << i
                if pressed & b:
                    nxt &= ~b
                    self.pending[i] += 1
                    if not self.desired & b:
                        self.pending[i] = 0
        toggled = nxt ^ self.latched
        for i in range(N_BITS):
            self.age[i] = 1 if toggled >> i & 1 else min(self.age[i] + 1, AGE_LONG)
        self.latched = nxt
        return nxt

    def exclusive(self, keep: int) -> None:
        """HoldFilter.Exclusive (the ACTION EXCLUSIVE flag): every key outside `keep` released on the next latch,
        below its minimum press if need be, and its queued edges dropped; then push the kept set as usual."""
        for i in range(N_BITS):
            b = 1 << i
            if keep & b:
                continue
            self.pending[i] = 0
            if self.latched & b:
                self.latched &= ~b
                self.age[i] = 0          # step() ages it to 1: released on this latch
        self.desired &= keep

    def queued(self, mask: int) -> bool:
        """Some key in `mask` has an edge requested but not latched yet."""
        return any(self.pending[i] for i in range(N_BITS) if mask >> i & 1)


def keys_clear(hf: Mapping | None, inflight: Sequence[int], press: int, allowed: int | None = None) -> bool | None:
    """Would a press of `press`, sent now to land after the `inflight` ACTION masks (sent but not applied yet, oldest
    first: the ones for the frames before the press's, plus any overdue), reach the game with no key outside `allowed`
    (default: `press`) latched or queued on its landing frame? Checked for the ways the in-flight ones can land: one per
    frame; all in the next input update (an overdue ACTION is applied with the next one, in arrival order); all in
    the press's own update (the brain missed a frame). None: no act.hf (unknown)."""
    if not isinstance(hf, Mapping) or "latched" not in hf:
        return None
    other = ((1 << N_BITS) - 1) & ~(press if allowed is None else allowed)
    base = Filter.from_hf(hf)
    ms = [int(m) for m in inflight]
    for how in ("frames", "next", "late"):
        f = base.copy()
        if how == "frames":
            for m in ms:
                f.step(m)
        elif ms and how == "next":
            for m in ms[:-1]:
                f.push(m)
            f.step(ms[-1])
        elif ms:
            f.step(f.desired)            # no ACTION this update: the filter holds the last set
            for m in ms:
                f.push(m)
        out = f.step(press)
        if out & other or f.queued(other):
            return False
    return True
