"""Immutable L2 plans and the generic foreground executor (Task 182; used only with SSBOT_FORUM_TWO_PLAN=1).

A plan is made once (usually by the resident worker, l2_plan_worker) and never changes: its parent scene, the bound
move instance, its generation, its times, its phases with their outputs and transitions, the scene's candidates and
the selected one, its support ranges. It holds no execution progress and it sends no key.

The executor is the only holder of execution state on the planner side: the active plan and phase, the handled events
of a move instance, waiting / blocked / expired / invalid / complete, the newest plan waiting for a legal boundary. It
knows no monster: the scene adapter (clapper_plans) turns observations into event names and resolves stance references;
the action owners below L2 keep every key, hit, bounce and hammer-tail responsibility. Replacing a plan changes L2's
preferences only: nothing here can rewrite a sent prefix, an absolute frame or an old target's clock.

Not a rule language: a phase is a fixed set of outputs, an event name maps to the next phase, a time maps to the next
phase, and that is all.
"""
from __future__ import annotations

from dataclasses import dataclass

DONE, INVALID, BLOCKED, HANDBACK = "done", "invalid", "blocked", "handback"
# handback: the plan cannot finish its goal from here and gives the rest to the public rules (not a success: the adapter keeps
# what is left of the goal for them)
TERMINAL = {DONE: "complete", INVALID: "invalid", BLOCKED: "blocked", HANDBACK: "handed_back"}
MAX_MOVES = 6                  # transitions in one tick: a guard against a phase cycle in a plan, never reached by design


@dataclass(frozen=True)
class Phase:
    """One stage's whole L2 output and how it ends. stance: a reference the scene adapter resolves each tick."""
    name: str
    target: int | None = None        # the attack target (None: the kept focus)
    attack: str | None = None        # the entry attack of this stage: side / stomp / None
    contact: str | None = None       # the contact style without a new entry
    ground: bool = False             # a way along the floor: rows without a jump key first among the safe ones
    stance: tuple | None = None
    no_hit: tuple = ()               # iids whose hits do not count in this stage
    suppress_hits: bool = False      # no hit on anyone and no entry attack in this stage
    on: tuple = ()                   # ((event name, next phase), ...), the first listed true event wins
    at: tuple | None = None          # (absolute game time, next phase): fixed in the plan, never moved by the executor
    replaceable: bool = True         # a newer generation may be adopted while this stage runs; its support is checked
    go: str | None = None            # the stance is reached by the action layer's bounded approach (guide / under / retreat)

    def after(self, event: str) -> str | None:
        return next((to for ev, to in self.on if ev == event), None)


@dataclass(frozen=True)
class Range:
    """A plan's support on one named value: the adapter measures it, outside [lo, hi] it no longer holds."""
    name: str
    lo: float
    hi: float

    def holds(self, value) -> bool:
        return value is not None and self.lo <= value <= self.hi


@dataclass(frozen=True)
class Candidate:
    """One of the scene's complete options: its hard feasibility (with the reason), applicability and first phase."""
    name: str
    feasible: bool
    reason: str | None = None
    start: str | None = None
    applicability: float = 1.0
    detail: tuple = ()               # ((key, value), ...): endpoint, wall room, route seconds, depart / arrival times

    def get(self, key, default=None):
        return next((v for k, v in self.detail if k == key), default)


@dataclass(frozen=True)
class Plan:
    scene: str
    instance: tuple                  # the bound move instance
    generation: int
    made_t: float                    # the game time of the snapshot it was made from
    aim_deadline: float | None       # the aim lock it was prepared for (None: past it, or unknown)
    valid_until: float
    phases: tuple = ()
    candidates: tuple = ()
    selected: str | None = None      # the scene's normal choice; None: the public selector chooses among the candidates
    status: str = "ok"               # ok / none (no feasible option: reason says why; never an empty route)
    reason: str | None = None
    support: tuple = ()              # Range: outside any of them an aim-stage plan is invalid
    soft: tuple = ()                 # Range: outside any of them an update is requested while planning time remains
    detail: tuple = ()               # ((key, value), ...): numbers the adapter's takeoff check uses

    def phase(self, name: str) -> Phase | None:
        return next((p for p in self.phases if p.name == name), None)

    def candidate(self, name: str | None) -> Candidate | None:
        return next((c for c in self.candidates if c.name == name), None)

    def get(self, key, default=None):
        return next((v for k, v in self.detail if k == key), default)

    def complete(self) -> bool:
        """Every transition and every feasible candidate's start lead to an existing phase or a terminal name."""
        names = {p.name for p in self.phases} | set(TERMINAL)
        if self.status != "ok":
            return True
        if not self.phases or len({p.name for p in self.phases}) != len(self.phases):
            return False
        if any(to not in names for p in self.phases for _, to in p.on) or any(
                p.at is not None and p.at[1] not in names for p in self.phases):
            return False
        feasible = [c for c in self.candidates if c.feasible]
        if not feasible or any(c.start not in names for c in feasible):
            return False
        return self.selected is None or any(c.name == self.selected for c in feasible)


class PlanExecutor:
    """The one owner of the running plan's progress. Non-blocking; nothing here waits for a worker."""

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.plan: Plan | None = None
        self.name: str | None = None      # the current phase's name
        self.selected: str | None = None
        self.since: float | None = None   # the game time the current phase was entered
        self.pending: Plan | None = None  # the newest plan waiting for a legal boundary
        self.status = "idle"              # idle / waiting / blocked / expired / invalid / interrupted / complete / handed_back
        self.reason: str | None = None
        self.history: dict = {}           # instance -> [(event, t)], the handled events of a move instance
        self.generations: dict = {}       # instance -> the highest generation ever offered (no out-of-order result)
        self.last_plan: Plan | None = None
        self.notes: list = []             # what happened this tick (drained by the adapter's log)
        self.changed = False              # a phase or a plan changed this tick

    # ---- reads ----

    @property
    def phase(self) -> Phase | None:
        return None if self.plan is None or self.name is None else self.plan.phase(self.name)

    def handled(self, instance, event: str) -> bool:
        return any(ev == event for ev, _ in self.history.get(instance, ()))

    # ---- facts ----

    def record(self, instance, event: str, t: float) -> None:
        self.history.setdefault(instance, []).append((event, t))

    def _note(self, what: str, **kw) -> None:
        self.notes.append(dict(what=what, **kw))

    # ---- plans ----

    def offer(self, plan: Plan, now: float, instance_now, values: dict) -> tuple[str, str | None]:
        """A finished plan arrives. ("adopted" | "pending" | "none" | "rejected", why). A later plan of the same instance
        wins only if its generation is newer; an old result can never overwrite a new one."""
        why = None
        if not plan.complete():
            why = "incomplete plan"
        elif plan.instance != instance_now:
            why = "instance changed"
        elif plan.generation <= self.generations.get(plan.instance, -1):
            why = "out of order"
        elif not plan.made_t - 1e-6 <= now <= plan.valid_until:
            why = "expired"
        if why is not None:
            self._note("rejected", scene=plan.scene, generation=plan.generation, reason=why)
            return "rejected", why
        self.generations[plan.instance] = plan.generation
        if plan.status != "ok":
            # No option in this update: an explicit no plan. A plan already running keeps its written conditions (its
            # observed checks at the lock decide); with none running the scene is explicitly blocked.
            self._note("no plan", scene=plan.scene, generation=plan.generation, reason=plan.reason)
            if self.plan is None:
                self.status, self.reason, self.last_plan = "blocked", plan.reason or "no feasible option", plan
                self.changed = True
            return "none", plan.reason
        bad = self._violated(plan, values)
        if bad is not None:
            why = "out of support: " + bad
            self._note("rejected", scene=plan.scene, generation=plan.generation, reason=why)
            return "rejected", why
        if self.plan is not None and self.plan.instance == plan.instance and self.phase is not None \
                and not self.phase.replaceable:
            self.pending = plan
            self._note("pending", scene=plan.scene, generation=plan.generation, phase=self.name)
            return "pending", "phase past its replacement boundary"
        self._adopt(plan, now)
        return "adopted", None

    @staticmethod
    def _violated(plan: Plan, values: dict) -> str | None:
        for rng in plan.support:
            if not rng.holds(values.get(rng.name)):
                return rng.name
        return None

    def _adopt(self, plan: Plan, now: float) -> None:
        keep = self.selected if (self.plan is not None and self.plan.instance == plan.instance) else None
        self.plan, self.pending, self.status, self.reason = plan, None, "waiting", None
        self.changed = True
        choice = plan.selected
        if choice is None and keep is not None and (plan.candidate(keep) or Candidate("", False)).feasible:
            choice = keep
        self._note("adopted", scene=plan.scene, generation=plan.generation, instance=list(plan.instance),
                   selected=choice)
        self.selected, self.name, self.since = None, None, None
        if choice is not None:
            self.select(choice, now)

    def select(self, name: str, now: float) -> bool:
        """The chosen candidate of the active plan starts (the plan's own choice, or the public selector's winner)."""
        cand = None if self.plan is None else self.plan.candidate(name)
        if cand is None or not cand.feasible or self.selected == name:
            return False
        self.selected, self.name, self.since = name, cand.start, now
        self.changed = True
        self._note("selected", candidate=name, phase=cand.start)
        return True

    def end(self, status: str, reason: str | None, now: float) -> None:
        if self.plan is not None:
            self.last_plan = self.plan
            self._note("ended", status=status, reason=reason, phase=self.name, scene=self.plan.scene,
                       generation=self.plan.generation)
        self.plan, self.name, self.selected, self.since = None, None, None, None
        self.status, self.reason = status, reason
        self.changed = True

    # ---- the tick ----

    def step(self, now: float, events_of, values_of, instance_of) -> Phase | None:
        """One non-blocking advance: instance, validity and support first, then the fixed times and the observed events
        of the current phase (events_of(phase) -> names; a handled event of the instance is recorded once).
        values_of(plan) / instance_of(plan): the adapter's facts for THAT plan, read from its own snapshot (a pending plan is
        checked against its own instance and prediction, whatever happened to the active one)."""
        if self.pending is not None and (self.plan is None or self.plan.instance != self.pending.instance
                                         or (self.phase is not None and self.phase.replaceable)):
            pending, self.pending = self.pending, None
            if (pending.instance == instance_of(pending) and now <= pending.valid_until
                    and self._violated(pending, values_of(pending)) is None):
                self._adopt(pending, now)
            else:
                self._note("rejected", scene=pending.scene, generation=pending.generation, reason="pending plan stale")
        if self.plan is None:
            return None
        if self.plan.instance != instance_of(self.plan):
            self.end("invalid", "instance changed", now)
            return None
        if now > self.plan.valid_until:
            self.end("expired", "past the plan's validity", now)
            return None
        for _ in range(MAX_MOVES):
            phase = self.phase
            if phase is None:
                break                      # waiting for the selector's choice
            if phase.replaceable:
                bad = self._violated(self.plan, values_of(self.plan))
                if bad is not None:
                    self.end("invalid", "out of support: " + bad, now)
                    return None
            nxt, ev = None, None
            if phase.at is not None and now >= phase.at[0]:
                nxt, ev = phase.at[1], "time"
            else:
                true = set(events_of(phase))
                for name, to in phase.on:          # the first listed true event wins, whatever order they were seen in
                    if name in true:
                        nxt, ev = to, name
                        break
            if nxt is None:
                break
            self.record(self.plan.instance, ev, now)
            self._note("event", event=ev, phase=phase.name, next=nxt)
            self.changed = True
            if nxt in TERMINAL:
                self.end(TERMINAL[nxt], ev, now)
                return None
            self.name, self.since = nxt, now
        return self.phase
