"""A boss's behaviour table reduced to what the forecaster and the planner read at run time (M2 W3; DESIGN §3.5.3,
§4.4 enemy file): Control states with dwell ranges and successors, attack families with their states, anchors and
damage sources per state, and which support templates exist.

    model = BossModel.load("BellBeast")             # knowledge/1.0.30000/enemies/BellBeast.json + _hitboxes.npz keys
    model.states["Charge"].dwell                     # (0.8805, 0.8948) game seconds, logged min / max
    model.anchor("BB_CHARGE", "Set L")               # Anchor(75.03, 5.49, +1): fixed, so the anchor template applies
    model.key("BB_CHARGE", "Charge", "anchor")       # "support/BB_CHARGE/Charge/anchor" or None

Why only min / max and the support edges: the forecaster's support must hold every logged instance (DESIGN §3.5.3
support vs probability), so dwell ranges are the logged extremes, never quantiles, and a successor is in support when
it was ever logged (behaviour_tables support_transitions); the Dirichlet probabilities are for scoring only.

The behaviour builder (ssbot.knowledge.behaviour_tables) imports the oracle IPC and so may not be imported here (the
import firewall, tests/test_import_firewall.py); this module reads its JSON output and the npz key list instead.
Bell Beast facts used through it (2026-10-01 build, 266 fights): Set L / Set R anchors fixed at x 75.03 / 95.72
(charge y 5.49, leap y 0.99; mirror +1 / -1), the first attack after the wake is a charge from Submerged Init with the
Set R anchor; the burst anchor y is 5.49 with x anywhere in 81.21-91.21 and a box centre fixed at (+-0.539, -2.68) from
it by flipX; the rage anchor is fixed at (86.21, 5.49); DropBell M2 appears only in phase P2 (presence 0.0 in the P1
instances of Burst Recovery, Dig In after a leap and the tails).
"""
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ssbot.core.bosses import BOSSES, BossSpec

REPO = Path(__file__).resolve().parents[3]
KNOWLEDGE = REPO / "knowledge" / "1.0.30000"
TAIL = "_tail"
SUPPORT = "support/"
FIXED_TOL_U = 0.01           # an anchor whose logged x / y range is narrower than this is fixed


@dataclass(frozen=True, slots=True)
class StateInfo:
    name: str
    dwell: tuple[float, float]                      # logged min / max game seconds in the state
    succ: tuple[tuple[str, float], ...]             # successors in support (no death states), smoothed p renormalised
    family: str | None = None                       # attack family the state belongs to (None: decision chain)


@dataclass(frozen=True, slots=True)
class Anchor:
    x: float
    y: float
    mirror: int


@dataclass(frozen=True, slots=True)
class Family:
    name: str
    start: str
    states: tuple[str, ...]
    directed: bool
    anchors: dict[str, Anchor]                      # direction key -> fixed anchor (Set L / Set R / "-")
    anchor_y: float | None                          # fixed y even when x varies (the burst)
    x_range: tuple[float, float]
    mirror: int                                     # mirror when the family is not directed
    box_offset: dict[bool, tuple[float, float]]     # flipX -> fixed (dx', dy) of the body box centre from the anchor
    sources: dict[str, frozenset[str]]              # state (or _tail) -> damage source type keys
    p2_only: dict[str, frozenset[str]]              # state -> sources logged in phase P2 only
    world_sources: dict[str, frozenset[str]]        # state -> sources of its world-frame template
    damage: int                                     # largest logged damage of any of its sources (masks)
    hazard: bool                                    # a source of a type that passes i-frames (not ENEMY)
    entry: dict[str, tuple[float, float]]           # state -> entry time since the attack start (min, max)
    path: np.ndarray | None = None                  # boss_path rows (t, n, x_min, x_max, y_min, y_max, x_mean, y_mean)


@dataclass(slots=True)
class BossModel:
    enemy: str
    boss_type: str
    control_fsm: str
    hp: float
    spec: BossSpec
    states: dict[str, StateInfo]
    families: dict[str, Family]
    attack_starts: dict[str, str]
    decision_states: tuple[str, ...]
    dir_states: dict[str, int]
    death_states: tuple[str, ...]
    phase_marks: dict[str, str]
    initial_phase: str
    keys: frozenset[str]
    p_burst: dict[str, float] = field(default_factory=dict)   # Bell Burst? -> Burst Pos by phase (probability only)
    rage_hp: float | None = None                    # Rage? -> Rage Pos at the first P1 decision with hp <= this

    @classmethod
    def load(cls, enemy: str = "BellBeast", table: Path | str | None = None, npz: Path | str | None = None
             ) -> "BossModel":
        path = Path(table) if table else KNOWLEDGE / "enemies" / f"{enemy}.json"
        d = json.loads(path.read_text("utf-8"))
        npz_path = Path(npz) if npz else path.with_name(d["templates"]["file"])
        with np.load(npz_path) as z:
            keys = frozenset(f[: -len("/meta")] for f in z.files if f.endswith("/meta"))
            paths = {f.split("/")[0]: z[f] for f in z.files if f.endswith("/boss_path")}
        return cls.from_table(d, keys, paths)

    @classmethod
    def from_table(cls, d: dict, keys: Iterable[str], paths: dict[str, np.ndarray] | None = None) -> "BossModel":
        spec_d = d["spec"]
        boss = BOSSES.get(d["boss_type"]) or BossSpec(d["boss_type"])
        deaths = boss.death_states or ("Death Broadcast",)
        edges = {}
        for e in d["graph"]["edges"]:
            if e["to"] in deaths:
                continue
            edges.setdefault(e["from"], []).append((e["to"], float(e.get("p") or 0.0)))
        families: dict[str, Family] = {}
        state_family: dict[str, str] = {}
        for fam, a in d["attacks"].items():
            for s in a["states"]:
                state_family.setdefault(s, fam)
            families[fam] = _family(fam, a, (paths or {}).get(fam))
        states = {}
        for s, q in d["dwell_s"].items():
            succ = edges.get(s, [])
            tot = sum(p for _, p in succ) or 1.0
            states[s] = StateInfo(s, (float(q.get("min", 0.0)), float(q.get("max", 0.0))),
                                  tuple((t, p / tot) for t, p in succ), state_family.get(s))
        for s, succ in d["support_transitions"].items():      # states without a dwell row (Dormant)
            if s not in states:
                ss = [(t, p) for t, p in edges.get(s, [])]
                states[s] = StateInfo(s, (0.0, 0.0), tuple(ss), state_family.get(s))
        return cls(enemy=d["enemy"], boss_type=d["boss_type"], control_fsm=d["fsms"][0], hp=float(d["hp"]),
                   spec=boss, states=states, families=families, attack_starts=dict(spec_d["attack_starts"]),
                   decision_states=tuple(spec_d["decision_states"]), dir_states=dict(spec_d["dir_states"]),
                   death_states=tuple(deaths), phase_marks=dict(spec_d.get("phase_marks") or {}),
                   initial_phase="P1", keys=frozenset(keys), p_burst=_burst_by_phase(d), rage_hp=_rage_hp(d))

    # ---- lookups ------------------------------------------------------------------------------------------------

    def key(self, family: str, state: str, frame: str) -> str | None:
        k = f"{SUPPORT}{family}/{state}/{frame}"
        return k if k in self.keys else None

    def anchor(self, family: str, direction: str | None) -> Anchor | None:
        """The fixed anchor of an attack made from this direction state, None when it varies or is unknown."""
        f = self.families[family]
        if direction is not None and direction in f.anchors:
            return f.anchors[direction]
        if not f.directed and len(f.anchors) == 1:
            return next(iter(f.anchors.values()))
        return None

    def directions(self, family: str) -> tuple[str, ...]:
        """Direction keys an attack of this family can come from (each with its fixed anchor), () when undirected."""
        f = self.families[family]
        return tuple(k for k in f.anchors if k in self.dir_states) if f.directed else ()

    def drawn(self, state: str) -> bool:
        """The boss is drawn (hittable) in this Control state (BossSpec.drawn)."""
        return state in self.spec.drawn


def _family(name: str, a: dict, path: np.ndarray | None) -> Family:
    an = a["anchor"]
    anchors: dict[str, Anchor] = {}
    x_lo, x_hi, y_fixed, mirror = np.inf, -np.inf, None, 1
    for k, v in an["by_dir"].items():
        sup = v.get("support") or {}
        xs, ys = sup.get("x"), sup.get("y")
        mirrors = [int(m) for m in (v.get("mirror") or {})]
        m = mirrors[0] if len(mirrors) == 1 else 1
        if xs is None or ys is None:
            continue
        x_lo, x_hi = min(x_lo, xs[0]), max(x_hi, xs[1])
        if ys[1] - ys[0] < FIXED_TOL_U:
            y_fixed = ys[0]
        if xs[1] - xs[0] < FIXED_TOL_U and ys[1] - ys[0] < FIXED_TOL_U:
            anchors[k] = Anchor(float(xs[0]), float(ys[0]), m)
        mirror = m
    box_offset: dict[bool, tuple[float, float]] = {}
    for k, v in (an.get("body_offset") or {}).get("by_dir_flip", {}).items():
        bc = v.get("box_centre")
        if not bc:
            continue
        dx, dy = bc["support"]["dx"], bc["support"]["dy"]
        if dx[1] - dx[0] < FIXED_TOL_U and dy[1] - dy[0] < FIXED_TOL_U:
            box_offset[k.endswith("True")] = (float(dx[0]), float(dy[0]))
    sources: dict[str, set[str]] = {}
    p2: dict[str, set[str]] = {}
    world: dict[str, set[str]] = {}
    damage, hazard = 1, False
    for h in a.get("hitboxes") or ():
        tk = h["source"].split(":")[0]
        sources.setdefault(h["state"], set()).add(tk)
        if h.get("frame") == "world":
            world.setdefault(h["state"], set()).add(tk)
        damage = max([damage] + [int(x) for x in h.get("dmg") or ()])
        hazard |= any(t not in ("ENEMY", "NON_HAZARD") for t in h.get("type") or ())
        pres = h.get("presence_by_phase") or {}
        if pres and pres.get("P1", 0.0) == 0.0 and pres.get("P2", 0.0) > 0.0:
            p2.setdefault(h["state"], set()).add(tk)
    entry = {s: (float(q["min"]), float(q["max"])) for s, q in a["state_entry_s"].items() if q.get("n")}
    return Family(name=name, start=a["start_states"][0], states=tuple(a["states"]), directed=bool(a.get("mirrored")),
                  anchors=anchors, anchor_y=y_fixed, x_range=(float(x_lo), float(x_hi)), mirror=mirror,
                  box_offset=box_offset, sources={k: frozenset(v) for k, v in sources.items()},
                  p2_only={k: frozenset(v) for k, v in p2.items()},
                  world_sources={k: frozenset(v) for k, v in world.items()}, damage=damage, hazard=hazard,
                  entry=entry, path=path)


def _burst_by_phase(d: dict) -> dict[str, float]:
    """P(Bell Burst? -> Burst Pos) per phase from the instance counts (probability only)."""
    a = d["attacks"]
    n = {ph: 0 for ph in ("P1", "P2")}
    b = dict(n)
    for fam, x in a.items():
        if fam == "BB_RAGE":
            continue
        for ph, c in (x.get("n_by_phase") or {}).items():
            n[ph] = n.get(ph, 0) + c
            if fam == "BB_BURST":
                b[ph] = b.get(ph, 0) + c
    return {ph: (b[ph] / n[ph] if n.get(ph) else 0.35) for ph in n}


def _rage_hp(d: dict) -> float | None:
    p2 = (d.get("phases") or {}).get("P2") or {}
    hp = p2.get("boss_hp_at_entry") or {}
    return float(hp["max"]) if hp.get("max") is not None else None
