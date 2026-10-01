"""Behaviour tables of a boss from combat logs (M2 W2; DESIGN §3.2.6 phase tables, §3.5.3 support vs probability,
§3.5.8 behaviour tables: counts, Dirichlet smoothing, quantiles; §4.4 enemy file).

    b = BehaviourBuilder(SPECS["BellBeast"])
    fights, skipped = run_fights(Path(r"C:\\ssbot\\data\\runs\\m2\\<run>"))     # closed recordings only
    for fight in fights + [human_fight(Path(r"C:\\ssbot\\data\\human\\<session>"), f0, f1)]:
        b.scan(fight)
    b.write(out_dir)          # <enemy>.json (§4.4 fields the data supports) + <enemy>_hitboxes.npz

Input: fights, i.e. frame ranges of STATE streams: combat-run recordings (one per AttemptRecord line of
<run>/attempts_i*.jsonl, frames f_wake..f_end) and human sessions (ssbot.tools.raw_session, a range given by hand).
Output (BehaviourBuilder.tables):
  graph      the boss's Control FSM edges with counts and, per source state, Dirichlet(ALPHA = 0.5) smoothed successor
             probabilities with one extra "unseen" outcome (p_unseen); worst_case = fewer than N_WORST = 30 exits
             logged (users then assume the fastest reachable attack, DESIGN §3.2.6 item 5). Edges into the death
             states are kept as support but not normalised (a kill can interrupt any state).
  dwell_s    per state game-time dwell quantiles (p0_5, p5, p50, p95, p99_5, n), from the frames of the fsm events
             (cumulative STATE "dt" = Time.deltaTime, so hit-stop counts as zero) with the FSM's own StateTime
             (t_in_prev) alongside; exits into a death state are left out.
  decisions  every branching state (>= 2 logged successors): selection counts conditioned on the hero relative to
             the boss (dx = hero - boss x, dy, side, |dx| bin of dist_bins_u), the hero's arena third and the phase.
             The boss is underground at Bell Beast's decisions, so its reference position is the last exported one.
  attacks    per attack family: instance counts (by phase and direction), state sequence, durations, anchor model,
             time-to-damage per state, hitbox windows (t_on / t_off quantiles from the attack start and from the
             state's entry), damage, reach extents, selection counts by distance bin.
  entities   every damage source seen: category, src bits, collider kinds, FSM states with the fraction of frames
             their damage colliders are enabled, what arms them, lifetimes.
The space-time templates (ssbot.knowledge.hitbox_tables) are accumulated in the same pass.

Attack instance: starts when the Control FSM enters an attack-start state (the per-encounter table), ends when it
returns to a decision state or the boss dies. It keeps the entry of every state, the boss trajectory, the hits taken
and every enabled damage collider per frame of the boss and of the entities armed during it. An entity is armed while
its FSM is out of the rest states or one of its damage colliders is enabled; it belongs to the instance current when
it armed and is followed after that instance ends until it disarms, stays out of the export for ABSENT_CLOSE_F frames
(left the view), or tail_max_s passes. Entities armed when a fight's scan starts are ambient and never attributed.

Measured on Bell Beast (trial run 20261001_121446, 2 data-policy episodes, plus the person's fight of 2026-09-30;
the built knowledge/1.0.30000/enemies/BellBeast.json adds the closed recordings of the 20261001_122249 run):
- The decision chain Submerged -> Rage? -> Bell Burst? -> Choose Dir -> Set L|R -> Move Choice -> attack start runs
  within one frame after Submerged's 1.000-1.017 s. Set L / Set R name the side the boss emerges on (x 75.03 /
  95.72; y 5.49 for the charge, 0.99 for the leap; flipX False / True) and it attacks toward the other side:
  Set L -> mirror +1, Set R -> mirror -1. The first attack after the wake comes straight from Submerged Init (no Set
  state; its direction comes from flipX at the anchor). Bell Burst? -> Burst Pos: 6 of 37 decisions in P1, 21 of 54
  in P2. Rage? -> Rage Pos exactly once per fight, at boss HP 70-75 (never at >= 80).
- The FSM's own StateTime (fsm event t_in_prev) equals the frame-time dwell for every Control state (max difference
  0.0 s over 30k frames).
- The boss is not in "ents" (not in the HealthManager active list) from Submerged through the antic states (Emerge
  Antic C/L, Burst Antic, Rage Pos/Antic), so the anchor is its first exported position: Charge Emerge 1.00-1.02 s,
  Leap Out 1.00-1.02 s, Burst Out 1.20-1.22 s, Rage Burst 2.23 s after the start. The burst emerges anywhere in
  x 81.3-91.2, unrelated to the hero (anchor - hero x p5..p95 -12.7..13.8 u).
- Boss colliders: a body box ("Boss Scene/Bone Beast" in damage events) and one poly, 7 points while charging,
  9 points while leaping ("PolyCollider", "LeapCollider"); all 2 masks, hazard ENEMY, parry bits COUNTER only.
- AtkBell L / R (hazard; damage_hero + projectile; circle r 1.274) are launched by Fire Bells from the boss x -+ 2,
  bounce along the floor at 12 u/s and stay armed 2.6 s (p50) until they leave the export, outliving the attack.
- DropBell L/L2/M/M2/R/R2 (hazard; damage_hero, some frames + projectile; circle r 1.274) hang at y 13.74; the
  collider is enabled from Air (falling) through Bounce Air / Submerge, 2.7 s (p50) after Position. The Rage pattern
  (Ptn L / Ptn R) drops them in sequence; after the Rage (phase P2) Burst Out and Leap Land also drop M2, whose x
  moves in Position, and it is still bouncing when the next attack starts.
"""
import bisect
import functools
import json
import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ssbot.ipc.ents import DAMAGE_FLAGS, DAMAGE_SRC, PARRY_BITS, SRC_BITS, bits, hazard_name, is_threat
from ssbot.knowledge import hitbox_tables as hb
from ssbot.train.encounters import BELL_BEAST as _BELL_BEAST_ENC

SCHEMA = 1
BUILD = "1.0.30000"
QUANTILES = (0.005, 0.05, 0.5, 0.95, 0.995)
QKEYS = ("p0_5", "p5", "p50", "p95", "p99_5")
ALPHA = 0.5
N_WORST = 30
TARGET_INSTANCES = 200        # M2 exit: >= 200 logged instances per A-class attack (DESIGN §5)
ABSENT_CLOSE_F = 30           # an armed entity missing from the export this long has left the view
STATE_KEYS = ("dt", "hero", "ents", "ev")
TAIL = "_tail"


@dataclass(frozen=True, slots=True)
class BehaviourSpec:
    """Per-encounter segmentation table."""
    enemy: str
    scene: str
    boss_type: str                     # entity type_key of the boss
    control_fsm: str
    hp: int
    dormant: tuple[str, ...]           # Control states before the wake
    death_states: tuple[str, ...]
    attack_starts: dict[str, str]      # Control state -> attack family
    decision_states: tuple[str, ...]   # the chain between attacks; entering one ends the current attack
    dir_states: dict[str, int]         # decision state -> mirror of the next attack (+1 faces +x, -1 faces -x)
    directed: tuple[str, ...]          # families that face a direction (mirrored anchor templates)
    phase_marks: dict[str, str]        # entering this Control state switches to that phase
    phases: dict[str, str]
    initial_phase: str
    world_fixed: tuple[str, ...]       # type_key prefixes of arena-fixed hazards (world-frame templates)
    rest_states: tuple[str, ...] = ("Init", "Dormant")   # FSM states of a hazard entity that mean "not armed"
    flip_mirror: tuple[int, int] = (1, -1)               # mirror for flipX False / True when no direction state
    dist_bins_u: tuple[float, ...] = (0.0, 3.0, 6.0, 10.0, 99.0)
    arena_x: tuple[float, float] = (0.0, 0.0)
    floor_y: float = 0.0
    tail_max_s: float = 6.0


BELL_BEAST = BehaviourSpec(
    enemy="BellBeast", scene=_BELL_BEAST_ENC.scene, boss_type=_BELL_BEAST_ENC.boss_type,
    control_fsm=_BELL_BEAST_ENC.control_fsm, hp=150, dormant=_BELL_BEAST_ENC.dormant,
    death_states=_BELL_BEAST_ENC.death_states,
    attack_starts={"Emerge Antic C": "BB_CHARGE", "Emerge Antic L": "BB_LEAP", "Burst Pos": "BB_BURST",
                   "Rage Pos": "BB_RAGE"},
    decision_states=("Submerged Init", "Submerged", "Rage?", "Bell Burst?", "Choose Dir", "Set L", "Set R",
                     "Move Choice"),
    dir_states={"Set L": 1, "Set R": -1}, directed=("BB_CHARGE", "BB_LEAP"),
    phase_marks={"Rage End": "P2"},
    phases={"P1": "from the wake until the Rage pattern ends", "P2": "after Rage End (DropBell M2 joins Bell Burst "
            "and Leap)"},
    initial_phase="P1", world_fixed=("BoneBeast DropBell",), arena_x=_BELL_BEAST_ENC.arena_x,
    floor_y=_BELL_BEAST_ENC.floor_y)

SPECS = {s.enemy: s for s in (BELL_BEAST,)}


# ---- small statistics --------------------------------------------------------------------------------------

def _r(x: float | None, nd: int = 4) -> float | None:
    return None if x is None or not math.isfinite(x) else round(float(x), nd)


def quantiles(values: Iterable[float], nd: int = 4) -> dict:
    """{p0_5, p5, p50, p95, p99_5, min, max, n} (linear interpolation); {"n": 0} when empty."""
    v = np.asarray([x for x in values if x is not None and math.isfinite(x)], np.float64)
    if v.size == 0:
        return {"n": 0}
    q = np.quantile(v, QUANTILES)
    out = {k: _r(x, nd) for k, x in zip(QKEYS, q)}
    out.update(min=_r(v.min(), nd), max=_r(v.max(), nd), n=int(v.size))
    return out


def dirichlet(counts: dict[str, int], alpha: float = ALPHA) -> tuple[dict[str, float], float]:
    """Posterior-mean successor probabilities under a symmetric Dirichlet(alpha) prior over the logged successors
    plus one "unseen" outcome: p_j = (n_j + alpha) / (N + alpha (K + 1)). Returns (p by successor, p_unseen)."""
    n = sum(counts.values())
    denom = n + alpha * (len(counts) + 1)
    return {k: (c + alpha) / denom for k, c in counts.items()}, alpha / denom


def dist_bin(d: float | None, edges: tuple[float, ...]) -> int | None:
    if d is None or not math.isfinite(d):
        return None
    i = int(np.searchsorted(np.asarray(edges), d, side="right")) - 1
    return min(max(i, 0), len(edges) - 2)


def collider_key(type_key: str, c: dict) -> str:
    kind = c.get("kind", "?")
    n = len(c.get("verts_world") or ()) // 2
    return f"{type_key}:{kind}{n}" if kind in ("poly", "edge") else f"{type_key}:{kind}"


# ---- fights (inputs) ---------------------------------------------------------------------------------------

@dataclass(slots=True)
class Fight:
    """One fight to scan: frames f0..f1 of a recording (kind "rec") or of a human session (kind "human")."""
    kind: str
    path: Path
    f0: int
    f1: int
    id: str
    outcome: str | None = None
    info: dict = field(default_factory=dict)


def recording_status(path: Path) -> str | None:
    try:
        return json.loads((Path(path) / "meta.json").read_text("utf-8")).get("status")
    except (OSError, json.JSONDecodeError):
        return None


def run_fights(run_dir: Path, closed_only: bool = True) -> tuple[list[Fight], list[str]]:
    """The fights of a combat run (ssbot.tools.combat_run): one per AttemptRecord with a wake frame, an end frame
    and a recording; with closed_only, recordings still being written (meta status != "closed") are skipped."""
    run_dir = Path(run_dir)
    fights, skipped = [], []
    for p in sorted(run_dir.glob("attempts_i*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                a = json.loads(line)
            except json.JSONDecodeError:
                skipped.append(f"{p.name}: unreadable line (being written?)")
                continue
            fid = f"{run_dir.name}/i{a.get('instance')}/ep{a.get('episode')}"
            if a.get("f_wake") is None or a.get("f_end") is None or not a.get("recording"):
                skipped.append(f"{fid}: no wake / end / recording ({a.get('outcome')}: {a.get('reason')})")
                continue
            rec = Path(a["recording"])
            if not rec.is_dir():  # moved run: the recording sits under <run>/rec/<date>/<profile>/<name>
                found = list(run_dir.glob(f"rec/*/*/{rec.name}"))
                rec = found[0] if found else rec
            status = recording_status(rec)
            if closed_only and status != "closed":
                skipped.append(f"{fid}: recording {rec.name} is {status or 'missing'}")
                continue
            fights.append(Fight("rec", rec, int(a["f_wake"]), int(a["f_end"]), fid, a.get("outcome"),
                                {"seed": a.get("seed"), "mode": a.get("mode"), "hits": a.get("hits"),
                                 "would_die": a.get("would_die")}))
    return fights, skipped


def human_fight(session: Path, f0: int, f1: int, outcome: str | None = None) -> Fight:
    session = Path(session)
    return Fight("human", session, int(f0), int(f1), f"human/{session.name}", outcome)


def raw_session_states(session: Path, f0: int | None = None, f1: int | None = None,
                       keys: tuple[str, ...] | None = None) -> Iterator[dict]:
    """STATE dicts with f0 <= f <= f1 from a human session's state.raw.zst (ssbot.tools.raw_session layout),
    streamed: frames before f0 are only peeked for "f", and reading stops after f1."""
    import zstandard

    from ssbot.ipc.framing import HEADER, MsgType
    from ssbot.record import formats

    with (Path(session) / "state.raw.zst").open("rb") as fh:
        rd = zstandard.ZstdDecompressor().stream_reader(fh, read_size=1 << 20)
        buf = bytearray()
        pos = 0
        while True:
            if len(buf) - pos < 4 or len(buf) - pos < 4 + int.from_bytes(buf[pos:pos + 4], "little"):
                del buf[:pos]
                pos = 0
                more = rd.read(1 << 22)
                if not more:
                    return
                buf += more
                continue
            n = int.from_bytes(buf[pos:pos + 4], "little")
            body = bytes(buf[pos + 4:pos + 4 + n])
            pos += 4 + n
            if body[0] != MsgType.STATE:
                continue
            flags = int.from_bytes(body[2:4], "little")
            payload = memoryview(body)[HEADER.size - 4:]
            f = formats.peek(payload, ("f",), flags).get("f")
            if not isinstance(f, int) or (f0 is not None and f < f0):
                continue
            if f1 is not None and f > f1:
                return
            yield formats.decode(payload, flags) if keys is None else formats.peek(payload, ("f", *keys), flags)


def fight_states(fight: Fight, keys: tuple[str, ...] | None = STATE_KEYS) -> Iterator[dict]:
    if fight.kind == "rec":
        from ssbot.record.recorder import RecordingReader
        return RecordingReader(fight.path).states(fight.f0, fight.f1, keys=keys)
    if fight.kind == "human":
        return raw_session_states(fight.path, fight.f0, fight.f1, keys=keys)
    raise ValueError(f"unknown fight kind {fight.kind!r}")


@functools.lru_cache(maxsize=2)
def _recording_events(path: Path, kinds: tuple[str, ...]) -> tuple[list[int], list[tuple[int, str, dict]]]:
    """A recording's events.jsonl of the given kinds, parsed once for all the fights in it: (frames, events)."""
    from ssbot.record.recorder import RecordingReader
    evs = sorted(((ev["frame"], ev["kind"], ev.get("data") or {}) for ev in RecordingReader(path).events(set(kinds))
                  if isinstance(ev.get("frame"), int)), key=lambda e: e[0])
    return [e[0] for e in evs], evs


def fight_events(fight: Fight, kinds: tuple[str, ...] = ("fsm", "damage")) -> Iterator[tuple[int, str, dict]]:
    """(frame, kind, data) of the fight's STATE events; a recording's events.jsonl avoids decoding STATEs."""
    if fight.kind == "rec" and (fight.path / "events.jsonl").is_file():
        frames, evs = _recording_events(Path(fight.path), tuple(kinds))
        yield from evs[bisect.bisect_left(frames, fight.f0):bisect.bisect_right(frames, fight.f1)]
        return
    for s in fight_states(fight, keys=("ev",)):
        for ev in s.get("ev") or ():
            if ev.get("k") in kinds:
                yield ev.get("f", s["f"]), ev["k"], ev.get("d") or {}


# ---- per-fight scan ----------------------------------------------------------------------------------------

@dataclass(slots=True)
class Transition:
    """One Control transition with its decision context (hero and boss world positions at that frame)."""
    fight: str
    f: int
    t: float                 # game time since the scan start (s)
    frm: str | None
    to: str
    t_in_prev: float | None
    hero_x: float | None
    hero_y: float | None
    boss_x: float | None
    boss_y: float | None
    boss_seen: str | None    # "live" (exported this frame), "last" (last exported position), None
    boss_hp: int | None
    phase: str

    @property
    def dx(self) -> float | None:
        return None if self.hero_x is None or self.boss_x is None else self.hero_x - self.boss_x

    @property
    def dy(self) -> float | None:
        return None if self.hero_y is None or self.boss_y is None else self.hero_y - self.boss_y


@dataclass(slots=True)
class Dwell:
    state: str
    dwell_s: float
    state_time_s: float | None
    to: str
    frames: int
    phase: str


@dataclass(slots=True)
class Sample:
    """One enabled damage collider in one frame of an attack instance."""
    t: float                 # s since the attack start
    state: str               # the boss's Control state then (TAIL once the attack is over)
    ts: float                # s since that state's entry (since the attack's end for TAIL)
    src: str                 # collider_key
    world: bool              # arena-fixed hazard (world frame) or anchor frame
    verts: np.ndarray        # (k, 2) world coordinates
    dmg: tuple               # (dealt, eff, hazard_type, flags, parry)


@dataclass(slots=True)
class EntitySeg:
    """One armed stretch of a non-boss damage entity."""
    iid: int
    type_key: str
    world: bool
    t_on: float              # s since the owner's start (game time since scan start when unowned)
    trigger: str | None      # boss Control state when it armed
    owner: "Instance | None"
    t_off: float | None = None   # last armed frame (same clock as t_on)
    last_f: int = 0
    last_t: float = 0.0
    end: str | None = None


@dataclass(slots=True)
class Instance:
    family: str
    phase: str
    fight: str
    f_start: int
    t_start: float
    dir: str | None
    mirror: int | None
    states: list                            # [(state, frame, s since start)], start state first
    ctx: Transition | None = None
    hero_start: tuple | None = None
    boss_hp: int | None = None
    f_end: int | None = None
    t_end: float | None = None              # s since start
    end: str | None = None                  # "rest" | "death" | "chain" | "fight_end"
    anchor: tuple | None = None
    anchor_t: float | None = None
    anchor_flip: bool | None = None
    path: list = field(default_factory=list)       # [(t, x, y)] boss world positions
    hits: list = field(default_factory=list)       # [(t, state, source, amount, hazard)]
    samples: list = field(default_factory=list)
    ents: list = field(default_factory=list)       # EntitySeg
    t_last: float = 0.0                             # last sample / tail time (s since start)

    def state_at(self, t: float) -> tuple[str, float]:
        """(Control state, s since its entry) at t s after the start; TAIL after the end."""
        if self.t_end is not None and t > self.t_end + 1e-9:
            return TAIL, t - self.t_end
        name, t0 = self.states[0][0], 0.0
        for st, _, ts in self.states:
            if ts <= t + 1e-9:
                name, t0 = st, ts
            else:
                break
        return name, t - t0


class FightScanner:
    """Streams one fight's STATEs into transitions, dwells and attack instances (handed to the builder)."""

    def __init__(self, spec: BehaviourSpec, fight_id: str, builder: "BehaviourBuilder"):
        self.spec, self.fight, self.b = spec, fight_id, builder
        self.T = 0.0
        self.last_f: int | None = None
        self.frames = 0
        self.gaps = 0
        self.hero: tuple | None = None
        self.boss_last: tuple | None = None     # (x, y, hp, f)
        self.boss_now = False
        self.ctl: str | None = None
        self.ctl_t: float | None = None
        self.ctl_f: int | None = None
        self.phase = spec.initial_phase
        self.dir: str | None = None
        self.cur: Instance | None = None
        self.done: list[Instance] = []          # ended, waiting for their armed entities to disarm
        self.segs: dict[int, EntitySeg] = {}
        self.ambient: set[int] = set()
        self.dead = False

    # ---- feed ----

    def feed(self, s: dict) -> None:
        f = s.get("f")
        if not isinstance(f, int) or (self.last_f is not None and f <= self.last_f):
            return
        dt = float(s.get("dt") or 0.0)
        if self.last_f is not None:
            gap = f - self.last_f
            if gap > 1:
                self.gaps += gap - 1
            self.T += dt * gap
        first = self.last_f is None
        self.last_f = f
        self.frames += 1
        hero = s.get("hero") or {}
        pos = hero.get("pos")
        if pos:
            self.hero = (float(pos[0]), float(pos[1]))
        ents = s.get("ents") or []
        boss = next((e for e in ents if e.get("type_key") == self.spec.boss_type), None)
        self.boss_now = boss is not None
        if boss is not None:
            self.boss_last = (float(boss["pos"][0]), float(boss["pos"][1]), boss.get("hp"), f)
        for ev in s.get("ev") or ():
            k, d = ev.get("k"), ev.get("d") or {}
            if k == "fsm" and d.get("fsm") == self.spec.control_fsm and self._is_boss(d.get("obj")):
                self._control(f, d)
            elif k == "damage":
                self._hit(f, d)
        self._boss(f, boss)
        self._entities(f, ents, boss, first)
        self._retire(f)

    def _is_boss(self, name) -> bool:
        b = self.spec.boss_type
        return isinstance(name, str) and (name == b or name.startswith(b + "(") or name.startswith(b + " ("))

    # ---- Control FSM ----

    def _context(self, f: int, frm, to: str, t_in_prev) -> Transition:
        bl = self.boss_last
        hx, hy = self.hero if self.hero else (None, None)
        return Transition(self.fight, f, self.T, frm, to, t_in_prev, hx, hy, bl[0] if bl else None,
                          bl[1] if bl else None, ("live" if self.boss_now else "last") if bl else None,
                          bl[2] if bl else None, self.phase)

    def _control(self, f: int, d: dict) -> None:
        spec = self.spec
        frm, to = d.get("from"), d.get("to")
        if not isinstance(to, str):
            return
        tr = self._context(f, frm, to, d.get("t_in_prev"))
        self.b.transitions.append(tr)
        if frm is not None and frm == self.ctl and self.ctl_t is not None and to not in spec.death_states:
            self.b.dwells.append(Dwell(frm, self.T - self.ctl_t, d.get("t_in_prev"), to, f - self.ctl_f, self.phase))
        self.ctl, self.ctl_t, self.ctl_f = to, self.T, f
        cur = self.cur
        if to in spec.death_states:
            if cur is not None:
                self._end(cur, f, "death")
            self.dead = True
        elif to in spec.attack_starts:
            if cur is not None:
                self._end(cur, f, "chain")
            fam = spec.attack_starts[to]
            mirror = spec.dir_states.get(self.dir) if fam in spec.directed else 1
            bl = self.boss_last
            self.cur = Instance(family=fam, phase=self.phase, fight=self.fight, f_start=f, t_start=self.T,
                                dir=self.dir if fam in spec.directed else None, mirror=mirror,
                                states=[(to, f, 0.0)], ctx=tr, hero_start=self.hero, boss_hp=bl[2] if bl else None)
            self.dir = None
        elif to in spec.decision_states:
            if cur is not None:
                self._end(cur, f, "rest")
            if to in spec.dir_states:
                self.dir = to
        elif cur is not None:
            cur.states.append((to, f, self.T - cur.t_start))
        elif to not in spec.dormant:
            self.b.counters[f"control state outside attacks: {to}"] += 1
        if to in spec.phase_marks:
            self.phase = spec.phase_marks[to]

    def _end(self, inst: Instance, f: int, reason: str) -> None:
        inst.f_end, inst.t_end, inst.end = f, self.T - inst.t_start, reason
        self.done.append(inst)
        if self.cur is inst:
            self.cur = None

    # ---- hits ----

    def _hit(self, f: int, d: dict) -> None:
        src = str(d.get("source"))
        owner = None  # the instance owning an armed entity named in the source (a bell still bouncing), else current
        for inst in ([self.cur] if self.cur else []) + self.done[::-1]:
            if any(seg.end is None and seg.type_key in src for seg in inst.ents):
                owner = inst
                break
        owner = owner or self.cur
        if owner is None:
            self.b.counters["hits outside attacks"] += 1
            self.b.loose_hits.append((self.fight, f, src, self.ctl))
            return
        t = self.T - owner.t_start
        st, _ = owner.state_at(t)
        owner.hits.append((t, st, src, int(d.get("amount") or 0), str(d.get("hazard"))))

    # ---- colliders ----

    @staticmethod
    def _dmg(c: dict) -> tuple:
        d = c["damage"]
        return d.get("dealt"), d.get("eff"), d.get("hazard_type"), d.get("flags"), d.get("parry")

    def _sample(self, inst: Instance, type_key: str, c: dict, world: bool) -> None:
        t = self.T - inst.t_start
        st, ts = inst.state_at(t)
        v = np.asarray(c["verts_world"], np.float32).reshape(-1, 2)
        inst.samples.append(Sample(t, st, ts, collider_key(type_key, c), world, v, self._dmg(c)))
        inst.t_last = max(inst.t_last, t)

    def _boss(self, f: int, boss: dict | None) -> None:
        if boss is None:
            return
        self.b.entity_frame(boss, self.ctl, boss=True)
        cur = self.cur
        threats = [c for c in boss.get("colliders") or () if is_threat(c)]
        if cur is None:
            if threats:
                self.b.counters[f"boss damage colliders outside attacks ({self.ctl})"] += 1
            return
        t = self.T - cur.t_start
        bx, by = float(boss["pos"][0]), float(boss["pos"][1])
        if cur.anchor is None:
            cur.anchor, cur.anchor_t, cur.anchor_flip = (bx, by), t, bool(boss.get("flipX"))
            if cur.mirror is None:
                cur.mirror = self.spec.flip_mirror[1 if cur.anchor_flip else 0]
        cur.path.append((t, bx, by))
        for c in threats:
            self._sample(cur, self.spec.boss_type, c, False)

    def _entities(self, f: int, ents: list, boss: dict | None, first: bool) -> None:
        spec = self.spec
        seen = set()
        for e in ents:
            if e is boss or not (int(e.get("src") or 0) & DAMAGE_SRC):
                continue
            iid, tk = e["iid"], e["type_key"]
            seen.add(iid)
            fsms = e.get("fsms") or ()
            fst = fsms[0]["state"] if fsms else None
            threats = [c for c in e.get("colliders") or () if is_threat(c)]
            armed = bool(threats) or (fst is not None and fst not in spec.rest_states)
            self.b.entity_frame(e, self.ctl, boss=False, fsm_state=fst, enabled=bool(threats))
            if first and armed:
                self.ambient.add(iid)
            if iid in self.ambient:
                continue
            seg = self.segs.get(iid)
            if armed and seg is None:
                owner = self.cur
                world = tk.startswith(spec.world_fixed)
                t_on = self.T - owner.t_start if owner else self.T
                seg = self.segs[iid] = EntitySeg(iid, tk, world, t_on, self.ctl, owner, last_f=f, last_t=t_on)
                if owner is not None:
                    owner.ents.append(seg)
                else:
                    self.b.counters[f"armed outside attacks: {tk}"] += 1
                self.b.arming(seg, owner)
            if seg is None:
                continue
            seg.last_f = f
            if not armed:
                self._close(seg, "disarmed")
                continue
            seg.last_t = self.T - seg.owner.t_start if seg.owner else self.T
            if seg.owner is not None:
                for c in threats:
                    self._sample(seg.owner, tk, c, seg.world)
        for iid, seg in list(self.segs.items()):
            if iid not in seen and f - seg.last_f > ABSENT_CLOSE_F:
                self._close(seg, "left view")
            elif seg.owner is not None and seg.owner.t_end is not None and \
                    self.T - seg.owner.t_start - seg.owner.t_end > spec.tail_max_s:
                self._close(seg, "tail cap")

    def _close(self, seg: EntitySeg, why: str) -> None:
        seg.end = why
        seg.t_off = seg.last_t
        self.segs.pop(seg.iid, None)

    def _retire(self, f: int) -> None:
        keep = []
        for inst in self.done:
            if any(seg.end is None for seg in inst.ents):
                keep.append(inst)
            else:
                self.b.add_instance(inst)
        self.done = keep

    def close(self) -> None:
        """End of the fight: close everything still open."""
        if self.cur is not None:
            self._end(self.cur, self.last_f or 0, "fight_end")
        for seg in list(self.segs.values()):
            self._close(seg, "fight_end")
        for inst in self.done:
            self.b.add_instance(inst)
        self.done = []


# ---- aggregation -------------------------------------------------------------------------------------------

class _PathAcc:
    """Boss positions (anchor frame) per time bin over instances: n, x/y min, max, sum."""

    def __init__(self):
        self.d: dict[int, list] = {}

    def add(self, b: int, x: float, y: float) -> None:
        r = self.d.get(b)
        if r is None:
            self.d[b] = [1, x, x, y, y, x, y]
        else:
            r[0] += 1
            r[1], r[2], r[3], r[4] = min(r[1], x), max(r[2], x), min(r[3], y), max(r[4], y)
            r[5] += x
            r[6] += y

    def array(self, bin_s: float) -> np.ndarray:
        """(nt, 8): t, n, x_min, x_max, y_min, y_max, x_mean, y_mean."""
        rows = [[b * bin_s, r[0], r[1], r[2], r[3], r[4], r[5] / r[0], r[6] / r[0]] for b, r in sorted(self.d.items())]
        return np.array(rows, np.float64).reshape(-1, 8)


@dataclass(slots=True)
class _InstSummary:
    """What is kept of an instance once its samples are rasterised."""
    family: str
    phase: str
    fight: str
    f_start: int
    dir: str | None
    mirror: int | None
    anchor: tuple | None
    anchor_t: float | None
    anchor_flip: bool | None
    hero_start: tuple | None
    boss_hp: int | None
    ctx: Transition | None
    states: list
    t_end: float | None
    end: str | None
    t_tail: float
    hits: list
    n_samples: int
    sources: list
    ttd: dict                # state -> s from its entry to the next enabled damage collider
    ttd_start: float | None
    path: np.ndarray | None  # (n, 3) t, x', y' (anchor frame), only with BehaviourBuilder(keep_paths=True)


class BehaviourBuilder:
    """Accumulates scanned fights into the behaviour tables and the space-time templates."""

    def __init__(self, spec: BehaviourSpec, cell: float = hb.CELL_U, bin_s: float = hb.BIN_S,
                 keep_paths: bool = False):
        self.spec, self.cell, self.bin_s, self.keep_paths = spec, cell, bin_s, keep_paths
        self.transitions: list[Transition] = []
        self.dwells: list[Dwell] = []
        self.instances: list[_InstSummary] = []
        self.fights: list[dict] = []
        self.counters: Counter = Counter()
        self.loose_hits: list = []
        self.acc: dict[str, hb.TemplateAccumulator] = {}
        self.paths: dict[str, _PathAcc] = defaultdict(_PathAcc)
        # (family, state, src) -> per-instance windows [t_on_state, t_off_state, t_on, t_off, phase]
        self.windows: dict[tuple, list] = defaultdict(list)
        self.src_info: dict[tuple, dict] = {}
        self.ent: dict[str, dict] = {}
        self.segs: list[tuple] = []          # (EntitySeg, family of its owner or None)
        self._n_inst = 0

    # ---- input ----

    def scan(self, fight: Fight, states: Iterable[dict] | None = None) -> dict:
        """Scan one fight (its STATEs from fight_states unless given). Returns a per-fight summary."""
        sc = FightScanner(self.spec, fight.id, self)
        n0 = len(self.instances)
        for s in fight_states(fight) if states is None else states:
            sc.feed(s)
        sc.close()
        info = {"id": fight.id, "kind": fight.kind, "f0": fight.f0, "f1": fight.f1, "outcome": fight.outcome,
                "frames": sc.frames, "gaps": sc.gaps, "game_s": _r(sc.T, 2), "instances": len(self.instances) - n0,
                "died": sc.dead}
        self.fights.append(info)
        return info

    def scan_states(self, states: Iterable[dict], fight_id: str = "states") -> dict:
        f = Fight("states", Path("."), -1, -1, fight_id)
        return self.scan(f, states)

    def entity_frame(self, e: dict, ctl: str | None, boss: bool, fsm_state: str | None = None,
                     enabled: bool = False) -> None:
        """Per type_key bookkeeping: category, src, collider kinds, frames per FSM state and enabled frames."""
        tk = e["type_key"]
        info = self.ent.get(tk)
        if info is None:
            info = self.ent[tk] = {"category": e.get("category"), "src": 0, "layers": set(), "colliders": Counter(),
                                   "radius": set(), "by_state": defaultdict(Counter), "boss": boss}
        info["src"] |= int(e.get("src") or 0)
        info["layers"].add(e.get("layer"))
        key = ctl if boss else fsm_state
        row = info["by_state"][key]
        row["frames"] += 1
        for c in e.get("colliders") or ():
            ck = collider_key("", c)[1:]
            info["colliders"][ck] += 1
            if c.get("r") is not None:
                info["radius"].add(round(float(c["r"]), 3))
            if is_threat(c):
                row[f"enabled {ck}"] += 1
        if enabled:
            row["enabled"] += 1

    def arming(self, seg: EntitySeg, owner: Instance | None) -> None:
        self.segs.append((seg, owner.family if owner else None))

    def _acc(self, key: str, frame: str) -> hb.TemplateAccumulator:
        k = f"{key}/{frame}"
        a = self.acc.get(k)
        if a is None:
            a = self.acc[k] = hb.TemplateAccumulator(k, frame, self.cell, self.bin_s)
        return a

    def add_instance(self, inst: Instance) -> None:
        """Rasterise an ended instance into the templates, keep its summary, drop its samples."""
        self._n_inst += 1
        iid = self._n_inst
        fam = inst.family
        first_dmg = None
        per_src: dict[tuple, list] = {}
        skipped = 0
        for smp in inst.samples:
            if smp.world:
                verts, frame = smp.verts, "world"
            elif inst.anchor is not None:
                verts, frame = hb.to_anchor(smp.verts, inst.anchor, inst.mirror or 1), "anchor"
            else:
                skipped += 1
                continue
            r = hb.rasterize(verts, self.cell)
            if r is None:
                continue
            self._acc(fam, frame).add_patch(int(round(smp.t / self.bin_s)), *r, instance=iid)
            self._acc(f"{fam}/{smp.state}", frame).add_patch(int(round(smp.ts / self.bin_s)), *r, instance=iid)
            first_dmg = smp.t if first_dmg is None else min(first_dmg, smp.t)
            w = per_src.get((smp.state, smp.src))
            vmin, vmax = verts.min(axis=0), verts.max(axis=0)
            if w is None:
                per_src[(smp.state, smp.src)] = [smp.ts, smp.ts, smp.t, smp.t, vmin, vmax, {smp.dmg}, frame]
            else:
                w[0], w[1] = min(w[0], smp.ts), max(w[1], smp.ts)
                w[2], w[3] = min(w[2], smp.t), max(w[3], smp.t)
                w[4], w[5] = np.minimum(w[4], vmin), np.maximum(w[5], vmax)
                w[6].add(smp.dmg)
        if skipped:
            self.counters["anchor-frame samples without an anchor"] += skipped
        for (state, src), w in per_src.items():
            self.windows[(fam, state, src)].append((w[0], w[1], w[2], w[3], inst.phase))
            info = self.src_info.get((fam, state, src))
            if info is None:
                info = self.src_info[(fam, state, src)] = {"lo": w[4], "hi": w[5], "dmg": set(), "frame": w[7],
                                                          "phases": Counter()}
            info["lo"], info["hi"] = np.minimum(info["lo"], w[4]), np.maximum(info["hi"], w[5])
            info["dmg"] |= w[6]
            info["phases"][inst.phase] += 1
        path = None
        if inst.anchor is not None and inst.path:
            path = np.array(inst.path, np.float64)
            path[:, 1] = (inst.mirror or 1) * (path[:, 1] - inst.anchor[0])
            path[:, 2] -= inst.anchor[1]
            pa = self.paths[fam]
            for t, x, y in path:
                pa.add(int(round(t / self.bin_s)), x, y)
        # time to damage: from each state entry (and the start) to the next enabled damage collider of the instance
        times = np.sort(np.array([s.t for s in inst.samples], np.float64))
        ttd = {}
        for st, _, ts in inst.states:
            i = int(np.searchsorted(times, ts - 1e-6))
            if i < len(times) and st not in ttd:
                ttd[st] = float(times[i] - ts) if times[i] > ts else 0.0
        t_tail = max([inst.t_end or 0.0, inst.t_last] + [s.t_off for s in inst.ents if s.t_off is not None])
        self.instances.append(_InstSummary(
            fam, inst.phase, inst.fight, inst.f_start, inst.dir, inst.mirror, inst.anchor, inst.anchor_t,
            inst.anchor_flip, inst.hero_start, inst.boss_hp, inst.ctx, list(inst.states), inst.t_end,
            inst.end, t_tail, inst.hits, len(inst.samples), sorted({s.src for s in inst.samples}), ttd,
            None if first_dmg is None else float(first_dmg),
            path.astype(np.float32) if self.keep_paths and path is not None else None))
        inst.samples = []

    # ---- output ----

    def families(self) -> list[str]:
        order = list(dict.fromkeys(self.spec.attack_starts.values()))
        return order + sorted({i.family for i in self.instances} - set(order))

    def graph(self) -> dict:
        spec = self.spec
        edges = Counter((t.frm, t.to) for t in self.transitions if t.frm is not None)
        out_by: dict[str, Counter] = defaultdict(Counter)
        kills: dict[str, Counter] = defaultdict(Counter)
        for (a, b), n in edges.items():
            (kills if b in spec.death_states else out_by)[a][b] += n
        states = sorted({s for e in edges for s in e} | {t.to for t in self.transitions})
        from_rows = {}
        edge_rows = []
        for a in sorted(set(out_by) | set(kills)):
            n = sum(out_by[a].values())
            p, p_unseen = dirichlet(dict(out_by[a]))
            from_rows[a] = {"n": n, "successors": dict(out_by[a].most_common()), "worst_case": n < N_WORST,
                            "p_unseen": _r(p_unseen), "kills": dict(kills[a])}
            for b, c in out_by[a].most_common():
                edge_rows.append({"from": a, "to": b, "n": c, "p": _r(p[b]), "p_mle": _r(c / n),
                                  "low_n": c < N_WORST})
            for b, c in kills[a].items():
                edge_rows.append({"from": a, "to": b, "n": c, "kill": True})
        starts = Counter(t.to for t in self.transitions if t.frm is None)
        return {"fsm": spec.control_fsm, "alpha": ALPHA, "n_worst": N_WORST, "states": states, "starts": dict(starts),
                "from": from_rows, "edges": edge_rows,
                "branching": sorted(a for a, c in out_by.items() if len(c) >= 2)}

    def dwell(self) -> dict:
        by: dict[str, list[Dwell]] = defaultdict(list)
        for d in self.dwells:
            by[d.state].append(d)
        out = {}
        for st, ds in sorted(by.items()):
            dw = [d.dwell_s for d in ds]
            row = quantiles(dw)
            row["state_time_s"] = quantiles([d.state_time_s for d in ds])
            row["frames"] = quantiles([d.frames for d in ds], 1)
            row["instant"] = max(dw) < 1e-9
            row["worst_case"] = len(ds) < N_WORST
            diffs = [abs(d.dwell_s - d.state_time_s) for d in ds if d.state_time_s is not None]
            row["max_abs_dwell_minus_state_time"] = _r(max(diffs)) if diffs else None
            by_to = defaultdict(list)
            for d in ds:
                by_to[d.to].append(d.dwell_s)
            if len(by_to) > 1:
                row["by_successor"] = {k: quantiles(v) for k, v in by_to.items()}
            out[st] = row
        return out

    def _arena_third(self, x: float | None) -> str | None:
        if x is None:
            return None
        a0, a1 = self.spec.arena_x
        w = (a1 - a0) / 3.0
        return "W" if x < a0 + w else ("E" if x >= a1 - w else "C")

    def decisions(self, branching: list[str]) -> dict:
        edges = self.spec.dist_bins_u
        out = {}
        for st in branching:
            trs = [t for t in self.transitions if t.frm == st and t.to not in self.spec.death_states]
            row = {"n": len(trs), "to": dict(Counter(t.to for t in trs).most_common()), "worst_case": len(trs) < N_WORST,
                   "boss_ref": dict(Counter(t.boss_seen for t in trs)), "dist_bins_u": list(edges)}
            by_bin: dict[str, Counter] = defaultdict(Counter)
            by_side: dict[str, Counter] = defaultdict(Counter)
            by_third: dict[str, Counter] = defaultdict(Counter)
            by_phase: dict[str, Counter] = defaultdict(Counter)
            ctx = defaultdict(lambda: {"dx": [], "dy": [], "hero_x": [], "boss_hp": []})
            for t in trs:
                dx = t.dx
                b = dist_bin(abs(dx) if dx is not None else None, edges)
                by_bin[str(b)][t.to] += 1
                by_side["L" if dx is not None and dx < 0 else ("R" if dx is not None else "?")][t.to] += 1
                by_third[str(self._arena_third(t.hero_x))][t.to] += 1
                by_phase[t.phase][t.to] += 1
                c = ctx[t.to]
                c["dx"].append(dx)
                c["dy"].append(t.dy)
                c["hero_x"].append(t.hero_x)
                c["boss_hp"].append(t.boss_hp)
            row["by_dist_bin"] = {k: dict(v) for k, v in sorted(by_bin.items())}
            row["by_side"] = {k: dict(v) for k, v in sorted(by_side.items())}
            row["by_hero_third"] = {k: dict(v) for k, v in sorted(by_third.items())}
            row["by_phase"] = {k: dict(v) for k, v in sorted(by_phase.items())}
            row["context"] = {to: {k: quantiles(v, 3) for k, v in c.items()} for to, c in ctx.items()}
            out[st] = row
        return out

    def attacks(self) -> dict:
        spec = self.spec
        edges = spec.dist_bins_u
        nb = len(edges) - 1
        out = {}
        for fam in self.families():
            ins = [i for i in self.instances if i.family == fam]
            states = list(dict.fromkeys(st for i in ins for st, _, _ in i.states))
            starts = sorted({i.states[0][0] for i in ins})
            sel: dict[str, list[int]] = {}
            for i in ins:
                dx = i.ctx.dx if i.ctx is not None else None
                b = dist_bin(abs(dx) if dx is not None else None, edges)
                if b is not None:
                    sel.setdefault(i.phase, [0] * nb)[b] += 1
            anchor = {"frame": "boss position at its first export in the instance",
                      "t_s": quantiles([i.anchor_t for i in ins]), "missing": sum(i.anchor is None for i in ins)}
            by_dir = defaultdict(list)
            for i in ins:
                by_dir[i.dir or "-"].append(i)
            anchor["by_dir"] = {d: {"n": len(v), "mirror": dict(Counter(str(i.mirror) for i in v)),
                                    "x": quantiles([i.anchor[0] for i in v if i.anchor]),
                                    "y": quantiles([i.anchor[1] for i in v if i.anchor]),
                                    "flipX": dict(Counter(str(i.anchor_flip) for i in v)),
                                    "x_minus_hero_x": quantiles([i.anchor[0] - i.hero_start[0] for i in v
                                                                 if i.anchor and i.hero_start])}
                                for d, v in sorted(by_dir.items())}
            hits = Counter()
            hits_state = Counter()
            for i in ins:
                for _, st, src, _, _ in i.hits:
                    hits[src] += 1
                    hits_state[st] += 1
            ttd = {st: quantiles([i.ttd[st] for i in ins if st in i.ttd]) for st in states}
            row = {
                "start_states": starts, "states": states, "n": len(ins),
                "n_by_phase": dict(Counter(i.phase for i in ins)), "n_by_dir": dict(Counter(i.dir or "-" for i in ins)),
                "ends": dict(Counter(i.end for i in ins)), "mirrored": fam in spec.directed,
                "boss_hp_at_start": quantiles([i.boss_hp for i in ins], 1),
                "duration_s": quantiles([i.t_end for i in ins if i.end == "rest"]),
                "tail_s": quantiles([i.t_tail for i in ins]),
                "state_entry_s": {st: quantiles([ts for i in ins for s2, _, ts in i.states if s2 == st])
                                  for st in states},
                "ttd_s": {"start": quantiles([i.ttd_start for i in ins]), **ttd},
                "anchor": anchor,
                "select": {"dist": "|hero x - boss x| at the decision, boss x = last exported", "dist_bins_u":
                           list(edges), "counts": sel},
                "hits_taken": {"n": sum(len(i.hits) for i in ins), "by_source": dict(hits.most_common()),
                               "by_state": dict(hits_state.most_common())},
                "coverage": {"n": len(ins), "target": TARGET_INSTANCES, "ok": len(ins) >= TARGET_INSTANCES},
                "hitboxes": self._hitboxes(fam),
            }
            out[fam] = row
        return out

    def _hitboxes(self, fam: str) -> list[dict]:
        rows = []
        for (f, state, src), ws in sorted(self.windows.items()):
            if f != fam:
                continue
            info = self.src_info[(f, state, src)]
            w = np.array([x[:4] for x in ws], np.float64)
            dealt = sorted({d[0] for d in info["dmg"] if d[0] is not None})
            eff = sorted({d[1] for d in info["dmg"] if d[1] is not None})
            haz = sorted({hazard_name(int(d[2])) for d in info["dmg"] if d[2] is not None})
            flags = sorted({n for d in info["dmg"] if d[3] for n in bits(int(d[3]), DAMAGE_FLAGS)})
            parry = sorted({n for d in info["dmg"] if d[4] for n in bits(int(d[4]), PARRY_BITS)})
            lo, hi = info["lo"], info["hi"]
            rows.append({
                "state": state, "source": src, "frame": info["frame"], "n": len(ws), "phases": dict(info["phases"]),
                "t0_state": _r(float(w[:, 0].min())), "t1_state": _r(float(w[:, 1].max())),
                "t0": _r(float(w[:, 2].min())), "t1": _r(float(w[:, 3].max())),
                "t_on_state": quantiles(w[:, 0]), "t_off_state": quantiles(w[:, 1]),
                "t_on": quantiles(w[:, 2]), "t_off": quantiles(w[:, 3]),
                "x": [_r(float(lo[0]), 3), _r(float(hi[0]), 3)], "y": [_r(float(lo[1]), 3), _r(float(hi[1]), 3)],
                "dmg": dealt, "eff": eff, "type": haz, "flags": flags, "parry": parry,
                "parryable": "clash" in parry or "force" in parry})
        return rows

    def entities(self) -> dict:
        out = {}
        seg_by = defaultdict(list)
        for seg, fam in self.segs:
            seg_by[seg.type_key].append((seg, fam))
        for tk, info in sorted(self.ent.items()):
            by_state = {}
            for st, c in sorted(info["by_state"].items(), key=lambda kv: str(kv[0])):
                frames = c["frames"]
                by_state[str(st)] = {"frames": frames, **{k: _r(v / frames, 3) for k, v in sorted(c.items())
                                                          if k.startswith("enabled")}}
            segs = seg_by.get(tk, [])
            out[tk] = {
                "category": info["category"], "src": bits(info["src"], SRC_BITS), "layers": sorted(
                    x for x in info["layers"] if x is not None),
                "colliders": dict(info["colliders"]), "radius": sorted(info["radius"]), "boss": info["boss"],
                "by_state": by_state, "armed": len(segs),
                "armed_by_family": dict(Counter(str(fam) for _, fam in segs)),
                "armed_at_boss_state": dict(Counter(str(s.trigger) for s, _ in segs).most_common()),
                "lifetime_s": quantiles([s.t_off - s.t_on for s, _ in segs if s.t_off is not None]),
                "end": dict(Counter(str(s.end) for s, _ in segs)),
                "world_frame": tk.startswith(self.spec.world_fixed)}
        return out

    def phases(self) -> dict:
        out = {k: {"desc": v} for k, v in self.spec.phases.items()}
        for st, ph in self.spec.phase_marks.items():
            out.setdefault(ph, {})["entered_at"] = st
            out[ph]["boss_hp_at_entry"] = quantiles([t.boss_hp for t in self.transitions if t.to == st], 1)
        return out

    def coverage(self, attacks: dict, graph: dict) -> dict:
        fams = {f: {"n": a["n"], "by_phase": a["n_by_phase"], "target": TARGET_INSTANCES,
                    "missing": max(0, TARGET_INSTANCES - a["n"])} for f, a in attacks.items()}
        return {"logged_instances_min": min((a["n"] for a in attacks.values()), default=0),
                "target": TARGET_INSTANCES, "families": fams,
                "fsm_edges_extracted": bool(graph["edges"]),
                "edges_n_lt_30": [f"{e['from']} -> {e['to']} ({e['n']})" for e in graph["edges"]
                                  if e["n"] < N_WORST and not e.get("kill")],
                "states_n_lt_30": [f"{s} ({r['n']})" for s, r in graph["from"].items() if r["worst_case"]],
                "fights": len(self.fights), "frames": sum(f["frames"] for f in self.fights),
                "game_s": _r(sum(f["game_s"] or 0 for f in self.fights), 1),
                "counters": dict(self.counters.most_common())}

    def tables(self) -> dict:
        spec = self.spec
        g = self.graph()
        atk = self.attacks()
        support = {a: sorted(set(r["successors"]) | set(r["kills"])) for a, r in g["from"].items()}
        obs = {}
        for fam, a in atk.items():
            for st in a["states"]:
                parry = any(h["parryable"] for h in a["hitboxes"] if h["state"] == st)
                obs.setdefault(st, {"fsm_states": [st], "families": [], "ttd_s": a["ttd_s"].get(st),
                                    "parryable": parry})["families"].append(fam)
        return {
            "schema": SCHEMA, "enemy": spec.enemy, "build": BUILD, "scene": spec.scene, "boss_type": spec.boss_type,
            "hp": spec.hp, "fsms": sorted({spec.control_fsm}), "phases": self.phases(),
            "sources": self.fights, "graph": g, "dwell_s": self.dwell(), "decisions": self.decisions(g["branching"]),
            "observable_phases": obs, "attacks": atk, "support_transitions": support, "entities": self.entities(),
            "coverage": self.coverage(atk, g),
            "templates": {"cell_u": self.cell, "bin_s": self.bin_s, "file": f"{spec.enemy}_hitboxes.npz",
                          "keys": "<family>/<frame> (t from the attack start), <family>/<state>/<frame> (t from "
                                  "the state's entry; _tail = after the attack ended, t from its end)",
                          "frames": {"anchor": "x' = mirror * (x - anchor x), y' = y - anchor y",
                                     "world": "world coordinates (arena-fixed hazards)"},
                          "instance_columns": list(INSTANCE_COLUMNS),
                          "instance_codes": {"phase": list(spec.phases), "dir": "dir_states value, 0 = none",
                                             "end": END_CODES},
                          "arrays": "<family>/instances (n, columns), state_t (n, states: s from the start, nan = "
                                    "not entered), state_f (entry frames, -1), state_names, fights, boss_path (t, n, "
                                    "x_min, x_max, y_min, y_max, x_mean, y_mean; anchor frame)"},
            "spec": {"attack_starts": spec.attack_starts, "decision_states": list(spec.decision_states),
                     "dir_states": spec.dir_states, "directed": list(spec.directed), "phase_marks": spec.phase_marks,
                     "world_fixed": list(spec.world_fixed), "rest_states": list(spec.rest_states),
                     "dist_bins_u": list(spec.dist_bins_u), "tail_max_s": spec.tail_max_s},
        }

    def templates(self) -> dict[str, hb.SpaceTimeTemplate]:
        out = {}
        for k, a in sorted(self.acc.items()):
            t = a.finish()
            if t is not None:
                out[k] = t
        return out

    def extra_arrays(self) -> dict[str, np.ndarray]:
        out = {}
        for fam, pa in self.paths.items():
            out[f"{fam}/boss_path"] = pa.array(self.bin_s)
        for fam in self.families():
            ins = [i for i in self.instances if i.family == fam]
            if not ins:
                continue
            states = list(dict.fromkeys(st for i in ins for st, _, _ in i.states))
            phases = list(self.spec.phases)
            rows, st_t = [], np.full((len(ins), len(states)), np.nan)
            st_f = np.full((len(ins), len(states)), -1, np.int64)
            for k, i in enumerate(ins):
                ax, ay = i.anchor if i.anchor else (np.nan, np.nan)
                hx, hy = i.hero_start if i.hero_start else (np.nan, np.nan)
                rows.append([i.f_start, phases.index(i.phase) if i.phase in phases else -1, i.mirror or 0,
                             self.spec.dir_states.get(i.dir, 0), ax, ay,
                             np.nan if i.anchor_t is None else i.anchor_t, hx, hy,
                             np.nan if i.boss_hp is None else i.boss_hp, np.nan if i.t_end is None else i.t_end,
                             i.t_tail, len(i.hits), END_CODES.get(i.end, -1)])
                for st, fr, ts in i.states:
                    j = states.index(st)
                    if np.isnan(st_t[k, j]):
                        st_t[k, j], st_f[k, j] = ts, fr
            out[f"{fam}/instances"] = np.array(rows, np.float64)
            out[f"{fam}/state_t"] = st_t
            out[f"{fam}/state_f"] = st_f
            if self.keep_paths:
                out[f"{fam}/paths"] = np.concatenate(
                    [np.column_stack([np.full(len(i.path), k, np.float32), i.path]) for k, i in enumerate(ins)
                     if i.path is not None] or [np.zeros((0, 4), np.float32)])
            out[f"{fam}/state_names"] = np.array(states)
            out[f"{fam}/fights"] = np.array([i.fight for i in ins])
        return out

    def write(self, out_dir: Path) -> tuple[Path, Path, dict]:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        tables = self.tables()
        tpls = self.templates()
        for key, summary in reach_summary(tpls).items():  # DESIGN §4.4 attacks.<A>.reach_union, per frame
            fam, frame = key.split("/")
            if fam in tables["attacks"]:
                tables["attacks"][fam].setdefault("reach_union", {})[frame] = {"npz": key, **summary}
        js = out_dir / f"{self.spec.enemy}.json"
        js.write_text(json.dumps(tables, indent=1, default=_json_default) + "\n", encoding="utf-8")
        npz = hb.save_templates(out_dir / f"{self.spec.enemy}_hitboxes.npz", tpls, self.extra_arrays())
        return js, npz, tables


INSTANCE_COLUMNS = ("f_start", "phase", "mirror", "dir", "anchor_x", "anchor_y", "anchor_t", "hero_x", "hero_y",
                    "boss_hp", "dur_s", "tail_s", "hits", "end")
END_CODES = {"rest": 0, "death": 1, "chain": 2, "fight_end": 3}


def reach_summary(tpls: dict[str, hb.SpaceTimeTemplate], max_boxes: int = 64) -> dict:
    """Per family template (<family>/<frame>): extent, active window, and a conservative box cover of the reach
    union (DESIGN §4.4 reach_union), coarsened to at most max_boxes boxes."""
    out = {}
    for key, t in tpls.items():
        if key.count("/") != 1:
            continue
        ext = t.extent()
        act = t.active()
        out[key] = {"frame": t.frame, "n_instances": t.n_instances,
                    "extent": [_r(v, 3) for v in ext] if ext else None,
                    "active_s": [_r(v, 4) for v in act] if act else None,
                    "cells": int(t.reach().sum()), "boxes": [[_r(v, 3) for v in b] for b in coarse_boxes(t, max_boxes)]}
    return out


def coarse_boxes(t: hb.SpaceTimeTemplate, max_boxes: int = 64) -> np.ndarray:
    """A conservative cover of the reach union with at most max_boxes boxes: the exact row-run cover, made coarser
    (the mask is max-pooled into larger cells) until it fits."""
    mask = t.reach()
    k = 1
    while True:
        if k == 1:
            m = mask
        else:
            ny, nx = (mask.shape[0] + k - 1) // k, (mask.shape[1] + k - 1) // k
            pad = np.zeros((ny * k, nx * k), bool)
            pad[:mask.shape[0], :mask.shape[1]] = mask
            m = pad.reshape(ny, k, nx, k).any(axis=(1, 3))
        b = hb.mask_boxes(m).astype(np.float64) * k
        if len(b) <= max_boxes or k >= max(mask.shape):
            break
        k *= 2
    b[:, [0, 2]] += t.ix0
    b[:, [1, 3]] += t.iy0
    return b * t.cell


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")
