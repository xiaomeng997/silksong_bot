"""Hit targets beyond the boss's body: objects a down spike bounces off and a slash recoils from (bells now; the bell
houses and Blasted Steps of the route later), from the registry knowledge/<game>/pogo_targets.yaml.

Why. The bot never hit a bell, it only dodged them: no model said it could. The game bounces a down spike off any
HERO_ATTACK-layer collider and off any TinkEffect that answers the hit (HeroDownAttack.OnTriggerEnter2D /
OnHitResponded), unless a NonBouncer is active; both bell kinds qualify (layer 17, TinkEffect, no NonBouncer, scene
bone_05_boss) in every state with the collider on. Recorded proof: in the data-policy run 20261001_122249 the three down
spikes that met a bell all bounced the hero (vy 17.4), one off an attack bell still rising at 28.8 u/s.
Which phases work is therefore only relative motion: the spike's box must meet the bell before the bell meets the
hurtbox (in one physics step the spike wins: DamageEnemies resolves in LateFixedUpdate, the HeroBox's buffered enemy hit
in SuperLateFixedUpdate, after the bounce's i-frames). The planner checks exactly that on the bell's predicted path, in
every timing lane.

Path. From the target's observed position and velocity, its Rigidbody2D at 50 Hz (semi-implicit Euler, g from the
registry: 60 x gravity_scale 1.1 for the bells), its ground contacts as the FSM handles them (`bounces`). The path is
usable (`ok`) while it is determined: not after a bounce whose side is random (a drop bell's, +-4 u/s; the next tick
sees the side), not after the target leaves (`stop`, the attack bell's 2 s End Timer). Two radii: nominal (the
collider's) for where a hit lands, certain (minus CERT_MARGIN_U) for the pogo gate, which also ends where the
prediction's drift could exceed that margin (CERT_MAX_S).

    reg = load_registry()
    tr = TargetTracker(reg); tr.update(ws, t)            # each frame (the Forecaster does)
    paths = tr.paths(ws, tk)                              # [TargetPath], tk: seconds from the observation
"""
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml

from ssbot.core.worldstate import WorldState

REPO = Path(__file__).resolve().parents[3]
REGISTRY = REPO / "knowledge" / "1.0.30000" / "pogo_targets.yaml"
STEP_S = 0.02                 # Unity fixed step in the game (attack bell vy 14 -> 12.68 in one step at g 66)
CERT_MARGIN_U = 0.35          # the certain contact circle: radius minus this (ORACLE positions, 50/60 Hz sampling)
CERT_MAX_S = 0.6              # ... and only this far ahead
UNKNOWN_LIFE_S = 0.25         # an attack bell first seen past its first bounce: its End Timer is unknown


@dataclass
class TargetSpec:
    prefix: str
    r: float
    states: frozenset
    recoil: bool = True
    cooldown_s: float = 0.0
    g: float = 0.0
    ground_y: float | None = None
    next_bounce: dict = field(default_factory=dict)
    bounces: list = field(default_factory=list)
    life_after_first_s: float | None = None


@dataclass
class TargetPath:
    type_key: str
    iid: int
    box: np.ndarray           # [T, 4] nominal circle's AABB per frame
    ok: np.ndarray            # [T] path determined, collider on
    cert: np.ndarray          # [T] usable for the pogo gate (ok and within CERT_MAX_S)
    r: float


def load_registry(path: Path | str | None = None) -> list[TargetSpec]:
    d = yaml.safe_load(Path(path or REGISTRY).read_text("utf-8")) or {}
    out = []
    for prefix, v in d.items():
        ph = v.get("physics") or {}
        out.append(TargetSpec(prefix, float(v["shape"]["circle"]), frozenset(v.get("states") or ()),
                              bool(v.get("recoil", True)), float(v.get("damage_cooldown_s", 0.0)),
                              float(ph.get("g", 0.0)), ph.get("ground_y"), dict(ph.get("next_bounce") or {}),
                              list(ph.get("bounces") or []), ph.get("life_after_first_bounce_s")))
    return out


def simulate(spec: TargetSpec, x: float, y: float, vx: float, vy: float, nb: int, life_s: float | None,
             tk: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Centre path sampled at tk (s) and whether it is determined there."""
    t_end = float(tk[-1]) if len(tk) else 0.0
    n = int(math.ceil(t_end / STEP_S)) + 2
    ts = np.arange(n) * STEP_S
    xs, ys, det = np.empty(n), np.empty(n), np.ones(n, bool)
    known = True
    gone = False
    for i in range(n):
        if life_s is not None and ts[i] > life_s:
            gone = True
        xs[i], ys[i], det[i] = x, y, known and not gone
        if gone:
            continue
        vy -= spec.g * STEP_S
        x += vx * STEP_S
        y += vy * STEP_S
        if spec.ground_y is not None and y <= spec.ground_y and vy < 0 and nb < len(spec.bounces):
            b = spec.bounces[nb]
            if b.get("stop"):
                gone = True
                continue
            y = spec.ground_y
            vy = float(b["vy"])
            if b.get("vx") == "random":
                vx = float(b.get("vx_mag", 0.0))
                known = False
            elif b.get("vx") != "keep":
                vx = math.copysign(float(b["vx"]), vx if vx != 0 else 1.0)
            if not b.get("repeat"):
                nb += 1
    cx = np.interp(tk, ts, xs)
    cy = np.interp(tk, ts, ys)
    ok = np.interp(tk, ts, det.astype(float)) >= 1.0
    return cx, cy, ok


class TargetTracker:
    """Registry targets in the WorldState and the bits of history their paths need (an attack bell's first bounce,
    for its End Timer)."""

    def __init__(self, specs: list[TargetSpec] | None = None):
        self.specs = load_registry() if specs is None else specs
        self.first_bounce: dict[int, float] = {}
        self.t = 0.0

    def spec_of(self, type_key: str) -> TargetSpec | None:
        for s in self.specs:
            if type_key.startswith(s.prefix):
                return s
        return None

    def reset(self) -> None:
        self.first_bounce.clear()

    def update(self, ws: WorldState, t: float) -> None:
        self.t = t
        seen = set()
        for e in ws.entities:
            sp = self.spec_of(e.type_key.v)
            if sp is None or not e.fsm:
                continue
            st, tau = e.fsm[0][1], e.fsm[0][2]
            seen.add(e.id)
            if st == "First Bounce" and e.id not in self.first_bounce:
                self.first_bounce[e.id] = t - tau
            elif st not in sp.states:
                self.first_bounce.pop(e.id, None)
        for iid in [i for i in self.first_bounce if i not in seen]:
            del self.first_bounce[iid]

    def paths(self, ws: WorldState, tk: np.ndarray) -> list[TargetPath]:
        out = []
        for e in ws.entities:
            sp = self.spec_of(e.type_key.v)
            if sp is None or not e.fsm or e.pos.conf <= 0 or e.vel.conf <= 0:
                continue
            st = e.fsm[0][1]
            if st not in sp.states or st not in sp.next_bounce:
                continue
            life = None
            if sp.life_after_first_s is not None and sp.next_bounce[st] >= 1:
                t0 = self.first_bounce.get(e.id)
                life = UNKNOWN_LIFE_S if t0 is None else max(0.0, sp.life_after_first_s - (self.t - t0))
            (x, y), (vx, vy) = e.pos.v, e.vel.v
            cx, cy, ok = simulate(sp, float(x), float(y), float(vx), float(vy), int(sp.next_bounce[st]), life, tk)
            box = np.stack([cx - sp.r, cy - sp.r, cx + sp.r, cy + sp.r], axis=1)
            out.append(TargetPath(e.type_key.v, e.id, box, ok, ok & (tk <= CERT_MAX_S), sp.r))
        return out


def octagon(r: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """A circle of radius r as the planner's polygon form (vertices on the circle: inside it, never over it):
    polys [8, 2] around the box origin (-r, -r), starts [0, 8], base (-r, -r)."""
    a = (np.arange(8) + 0.5) * (2 * np.pi / 8)
    polys = np.stack([r * np.cos(a), r * np.sin(a)], axis=1)
    return polys, np.array([0, 8], np.int64), np.array([-r, -r])
