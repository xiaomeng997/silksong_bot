"""Experimental native chain proposals; the old planner remains the only selector.

Each row starts with the chain's current command and borrows an ordinary
planner completion. These alternatives are NOT predictions of future chain
decisions or hit/exit certificates. Without completions, a test probe may use a
single pulse followed by neutral release. It gets the ordinary planner's physics, scoring and escape checks.
Hook motion has no ordinary rollout here and is explicitly not executable yet.
Unfitted v0.1 admission requires an explicit named probe; nothing is enabled by
default. Transport success commits logical intent, never hero contact/protection.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
import json
from pathlib import Path
import time

import numpy as np

from .knife_chain_admission import evaluate_admission
from .knife_chain_history import HistView
from .knife_chain_native import NativeChainAudit, NativeChainAuditError


def rows_allowed(commands, allowed_mask):
    """Supervisor primitives for the actual command bits, including exit dashes."""
    from ssbot.core.primitives import Prim
    from .knife_chain_format import MASK_NAMES as B
    commands = np.asarray(commands, np.int64)
    allowed = np.asarray(allowed_mask, bool)
    result = np.ones(len(commands), bool)
    known = B["L"] | B["R"] | B["J"] | B["A"] | B["DASH"] | B["U"] | B["D"]
    for i, row in enumerate(commands):
        if np.any(row & ~known) or np.any((row & B["U"] != 0) & (row & B["D"] != 0)):
            result[i] = False
            continue
        needs = set()
        for m in row:
            if m == 0: needs.add(Prim.WAIT)
            if m & (B["L"] | B["R"]): needs.add(Prim.MOVE)
            if m & B["J"]: needs.update((Prim.JUMP, Prim.DOUBLEJUMP, Prim.WALLJUMP, Prim.GLIDE))
            if m & B["DASH"]: needs.add(Prim.DASH)
            if m & B["D"]: needs.add(Prim.ATTACK_DOWN)
            if m & B["U"] and not m & B["A"]: needs.add(Prim.INTERACT_UP)
            if m & B["A"]:
                needs.add(Prim.ATTACK_DOWN if m & B["D"] else Prim.ATTACK_UP if m & B["U"] else Prim.ATTACK_SIDE)
        result[i] = all(allowed[int(p)] for p in needs)
    return result


class NativeChainCandidates(NativeChainAudit):
    candidate_generation = True
    def __init__(self, *, runner_factory, probe_ref, journal=None, trace_limit=2048):
        if not isinstance(probe_ref, str) or not probe_ref.strip():
            raise ValueError("native unfitted chains require a named probe_ref")
        self.runner_factory = runner_factory
        self.probe_ref = probe_ref
        self.journal = journal
        self._journal_file = None
        super().__init__(trace_limit=trace_limit)

    @classmethod
    def from_env(cls, *, journal):
        import os
        from .knife_chain_slam import load_runner
        if not journal:
            raise ValueError("native chain probes require a journal path")
        return cls(runner_factory=load_runner, probe_ref=os.environ.get("SSBOT_FORUM_CHAIN_PROBE", ""),
                   journal=journal)

    def reset(self, episode, *, start_frame=None):
        self.flush()
        self.runner = self.runner_factory()
        self._draft = None
        self._offer = None
        self._context = None
        self._ticks = deque(maxlen=1200)
        self._receipts = {}
        self._pending = {}
        self._clock = 0.0
        self._clock_known = True
        self._slam0_seen = {}
        super().reset(episode, start_frame=start_frame)

    def _note(self, event, **data):
        super()._note(event, **data)
        if self.journal:
            if self._journal_file is None:
                path = Path(self.journal)
                path.parent.mkdir(parents=True, exist_ok=True)
                self._journal_file = path.open("a", encoding="utf-8")
            self._journal_file.write(json.dumps(self.events[-1], ensure_ascii=False, separators=(",", ":")) + "\n")

    def flush(self):
        if self._journal_file is not None:
            self._journal_file.flush()

    def _abandon(self, why):
        if self.runner.run is not None:
            self._note("chain_interrupted", frame=self.last_observed, link=self.runner.run.lid, reason=why)
        self.runner.reset()
        self._draft = self._offer = None

    def begin(self, state, history=()):
        # A policy error/early return may have skipped the prior send callback.
        if self._draft is not None:
            self._abandon("previous draft had no successful send")
        super().begin(state, history)
        self._context = None

    def observe(self, state):
        f = state["f"]
        previous = self.last_observed
        if previous is not None and f <= previous:
            return
        if previous is not None and f != previous + 1:
            self._abandon("missing STATE; queued actions are retained")
            self._ticks.clear()
        dt = state.get("dt")
        if not isinstance(dt, (int, float)) or not np.isfinite(dt) or dt < 0:
            self._clock_known = False
        else:
            self._clock += dt
        from .slam_play import clappers, control
        for e in clappers(state):
            if control(e)[0] == "Slam 0":
                self._slam0_seen.setdefault(e["iid"], f)
            elif control(e)[0] == "Slam Antic":
                self._slam0_seen.pop(e["iid"], None)
        act = state.get("act") or {}
        target = act.get("target")
        if target in self._pending:
            wanted = self._pending[target]
            desired = (act.get("hf") or {}).get("desired")
            applied = act.get("applied")
            if type(applied) is int and target <= applied <= f:
                self._pending.pop(target)
                if desired != wanted:
                    self._note("chain_application_unknown" if desired is None else "chain_application_mismatch",
                               frame=f, target=target, desired=desired, wanted=wanted)
                    self._abandon("oracle desired receipt differs or is unavailable")
                else:
                    self._note("chain_application_observed", frame=f, target=target,
                               applied=applied, hero_action="unchecked", contact="unchecked")
        for overdue in [t for t in self._pending if t < f - 2]:
            self._pending.pop(overdue)
            self._note("chain_application_unknown", frame=f, target=overdue, reason="not observed before deadline")
            self._abandon("oracle action application unobserved")
        super().observe(state)

    def prepare(self, state, *, ground, accepting, sim, guard=None, bombs=None):
        f = state["f"]
        if f != self.dispatch.frame or not self._clock_known:
            self._note("chain_unchecked", frame=f, reason="decision identity or game clock unavailable")
            return
        tick = (f, deepcopy(state), self._clock, bool(ground), bool(accepting))
        if not self._ticks or self._ticks[-1][0] != f:
            self._ticks.append(tick)
        self._context = (tick, sim, guard, bombs)

    def rows(self, *, T, origin, prefix, hold, hero_state, completions=None):
        """One fresh proposal, registered later at its actual planner row index."""
        if self._context is None:
            return None
        if type(T) is not int or T < 1:
            raise NativeChainAuditError("native horizon must be positive")
        tick, sim, guard, bombs = self._context
        f, state, game, ground, accepting = tick
        if origin != f or len(prefix) != 1 or sim.fo != origin or sim.f != f:
            self._note("chain_unchecked", frame=f, reason="lagged model origin is not supported")
            return None
        receipt = self._receipts.get(f + 1)
        if receipt is None or int(prefix[0]) != receipt:
            self._note("chain_unchecked", frame=f, reason="in-flight desired prefix has no matching send receipt")
            return None
        from .knife_chain_format import MASK_NAMES
        if np.any(np.asarray(prefix, np.int64) & MASK_NAMES["CLAW"]):
            self._note("chain_unchecked", frame=f, reason="queued hook has no native rollout adapter")
            return None
        from .slam_play import clappers, control
        enemies = clappers(state)
        if len(enemies) != 1:
            self._note("chain_unchecked", frame=f, reason="v0.1 native scope requires one living Clapper")
            return None
        e = enemies[0]
        hist = HistView(list(self._ticks), self._receipts, f, lag=self.runner.cfg0.get("lag", 0))
        # No private old-script state and no zero-padding of unknown sent keys.
        an = hist.antic(e["iid"], "Slam Antic", ())
        full_history = (an is not None and an["first_tick"] == an["fa"] and
                        all(F in self._receipts for F in range(an["fa"] + 1, f + 2)))
        self.runner.anchor.hist = hist
        self.runner.anchor.external = self.runner.run is None and full_history
        if self.runner.run is None and control(e)[0] != "Slam Antic" and not full_history:
            self._note("chain_unchecked", frame=f, reason="external entry needs complete observable history")
            return None
        t0 = time.perf_counter_ns()
        # The ported family never writes its rule records, binding or registry.
        # Sharing these removes repeated copies of 29 validated links, while its
        # plans, observation history, inputs and all action-dependent state stay private.
        static = (self.runner.chains, self.runner.P, self.runner.cfg0, self.runner.binding,
                  getattr(self.runner.anchor, "chains", None), getattr(self.runner.anchor, "cfg", None))
        preview = self.runner.preview(f, state, ground, accepting, t_game=game, sim=sim, guard=guard, bombs=bombs,
                                      static_context=tuple(x for x in static if x is not None))
        ms = (time.perf_counter_ns() - t0) / 1e6
        run = preview.draft.run
        if preview.mask is None or run is None:
            self._note("chain_no_proposal", frame=f, generation_ms=ms)
            return None
        mask = int(preview.mask)
        lid = run.lid
        from .knife_chain_format import MASK_NAMES
        if mask & MASK_NAMES["CLAW"] or str((state.get("hero") or {}).get("anim", {}).get("clip", "")).startswith("Harpoon"):
            self._note("chain_unchecked", frame=f, link=lid, reason="hook motion needs a native rollout adapter",
                       generation_ms=ms)
            return None
        if run.link in ("after", "air") and self._slam0_seen.get(e["iid"], f) > f - 2:
            self._note("chain_unchecked", frame=f, link=lid, reason="exit observation lacks two-frame lead")
            return None
        admission = evaluate_admission(preview.draft.chains[run.chain].admission[run.link], {}, frame=f)
        offer = self.dispatch.offer(lid, mask, table_ref=self.runner.binding["table_digest"], admission=admission)
        projection = "pulse_release"
        available = 1
        if completions is None:
            cmd = np.zeros((1, T), np.int64)
            cmd[0, 0] = mask
        else:
            ordinary = np.asarray(completions, np.int64)
            if ordinary.ndim != 2 or ordinary.shape[1] != T or not len(ordinary):
                raise NativeChainAuditError("ordinary completion table does not match native horizon")
            # Prefer the existing family with this exact first command; otherwise
            # use WAIT's ordinary continuations. Only index zero is ever sent.
            same = ordinary[ordinary[:, 0] == mask]
            if not len(same): same = ordinary[ordinary[:, 0] == 0]
            if not len(same): same = ordinary[:1]
            _, indices = np.unique(same[:, 1:], axis=0, return_index=True)
            available = len(indices)
            cmd = same[np.sort(indices)[:32]].copy()
            cmd[:, 0] = mask
            projection = "ordinary_completions"
        self._draft, self._offer = preview.draft, offer
        self._note("chain_proposal", frame=f, link=lid, mask=mask, generation_ms=ms,
                   admission=admission.verdict, probe_ref=self.probe_ref, projection=projection, T=T,
                   rows=len(cmd), available_completions=available, capped=available > len(cmd),
                   external=deepcopy(run.entered), hook_motion="unchecked")
        return cmd, ["CHAIN " + lid + ("" if len(cmd) == 1 else f"/{q}") for q in range(len(cmd))]

    def register_candidate(self, index):
        if self._offer is None:
            raise NativeChainAuditError("native row without a current draft")
        self.register_row(index, self._offer, probe_ref=self.probe_ref)

    def row_results(self, index, *, allowed, enveloped, unsafe, safe, score):
        self._note("chain_row_evaluated", frame=self.dispatch.frame, row=index, allowed=bool(allowed),
                   enveloped=bool(enveloped), unsafe=bool(unsafe), safe=bool(safe), score=float(score))

    def sent(self):
        sent = super().sent()
        self._receipts[sent.target_frame] = sent.desired_mask
        # Keep the bounded external-entry history; the immutable dispatch/journal
        # still retains every successful send, including already queued actions.
        for old in [f for f in self._receipts if f < sent.frame - 1202]:
            del self._receipts[old]
        if sent.chain_outcome == "sent" and self._draft is not None and sent.selection.offer is self._offer:
            self.runner = self._draft
            self._draft = self._offer = None
            self._pending[sent.target_frame] = sent.desired_mask
            self._note("chain_intent_committed", frame=sent.frame, target=sent.target_frame,
                       link=self.runner.run.lid, physical_action="unchecked", contact="unchecked")
        else:
            self._abandon("row unselected or final owner/keys overridden")
        self.flush()
        return sent

    def send_failed(self, error):
        super().send_failed(error)
        self._abandon("transport failed")
        self.flush()

    def summary(self):
        self.flush()
        return {**super().summary(), "mode": "native_probe", "candidate_generation": True,
                "projection": "ordinary_completions", "probe_ref": self.probe_ref,
                "journal": str(self.journal) if self.journal else None,
                "active_link": None if self.runner.run is None else self.runner.run.lid,
                "hook_motion": "unchecked", "closed_loop_future": "unchecked",
                "pending_application": sorted(self._pending),
                "live_ready": False, "journal_scope": "episode._act and observed inbox; not a full STATE archive"}
