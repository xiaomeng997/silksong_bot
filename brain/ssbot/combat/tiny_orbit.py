"""The Maestro's Tinies (Song Automaton Tiny) one by one (forum_planner_plan §5 R5 note: the Tiny orbit model; scoring
only until its held-out containment is 100 %, then the R2 cluster union can be replaced).

Statics (Maestro Control FSM, scene bundle; forum.md §17.4):
- Defend Start sends DEFEND READY to its three flies; Defending (1.75 s) rotates the "Defense Formation" child (local
  (0, -0.22)) by -180 deg/s and eases its scale 0.5 -> 2.5 in 0.75 s (EaseFloat easeOutSine); Defense Point 1-3 sit
  at radius 2 (local) at 90 / -30 / 210 deg, so the orbit is radius 1 -> 5 u around the Maestro, 120 deg apart, and
  each fly follows its point (Defend Ready, then Defend Buzz). The person 2026-10-05: this is the only orbit; before
  the defend the flies hover over the Maestro (Idle Pos (+-3, 2.5) / (0, 4.5)).
- Fire Antic: GetRandomChild of "Ready Flies" (the flies parented there, i.e. hovering in Ready) gets FIRE READY at
  once, FIRE 0.7 s later (Slash 1): which fly charges is known 0.7 s ahead; the charge goes about 45 deg down.

    orb = TinyOrbit.load()                                # knowledge/.../forum/tiny_orbit.json (tools.tiny_orbit fit)
    pts = orb.predict(tiny_xy, maestro_xy, maestro_v, age_s, horizons)   # [len(horizons), 2] fly centres

The fitted constants (angular rate, radius by defend age, the margin that held-out fights needed) are measured, not
assumed; see ssbot.tools.tiny_orbit.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

TINY_ORBIT_PATH = Path(__file__).resolve().parents[3] / "knowledge" / "1.0.30000" / "enemies" / "forum" / \
    "tiny_orbit.json"
CENTER_OFF = (0.0, -0.22)       # Defense Formation local position (Maestro scale 1)
OMEGA_STATIC = -180.0           # deg / s, Rotate zAngle (the measured sign and rate are in the fitted file)
SCALE_EASE = (0.5, 2.5, 0.75)   # Defending: Defense Scale 0.5 -> 2.5 over 0.75 s (easeOutSine)
POINT_R = 2.0                   # Defense Point distance from the formation centre (local)
DEFENDING_S = 1.75


def static_radius(age_defending: float) -> float:
    """The defense point's radius (u) at this age of Defending (the FSM's ease, before the flies' lag)."""
    a0, a1, d = SCALE_EASE
    x = min(max(age_defending / d, 0.0), 1.0)
    return POINT_R * (a0 + (a1 - a0) * math.sin(0.5 * math.pi * x))


@dataclass(slots=True)
class TinyOrbit:
    omega_deg_s: dict = field(default_factory=lambda: {0: OMEGA_STATIC, 1: -OMEGA_STATIC})  # by the Maestro's flipX
    r_age: list = field(default_factory=list)       # [[age since Defend Start (s), median radius]]
    center_off: tuple = CENTER_OFF
    margin_u: dict = field(default_factory=dict)    # horizon (s) -> held-out error to contain 100 % (u)
    bounds: tuple = (-math.inf, math.inf, -math.inf, math.inf)   # x0, x1, y0, y1 a fly centre stays in (terrain)

    @classmethod
    def load(cls, path: Path | None = None) -> "TinyOrbit":
        d = json.loads(Path(path or TINY_ORBIT_PATH).read_text("utf-8"))
        return cls({int(k): float(v) for k, v in d["omega_deg_s"].items()}, d["r_age"], tuple(d["center_off"]),
                   {float(k): float(v) for k, v in (d.get("margin_u") or {}).items()},
                   tuple(d.get("bounds") or (-math.inf, math.inf, -math.inf, math.inf)))

    def radius(self, age: float) -> float:
        if not self.r_age:
            return static_radius(age - 0.25)
        ages = [a for a, _ in self.r_age]
        rs = [r for _, r in self.r_age]
        return float(np.interp(age, ages, rs))

    def predict(self, tiny: tuple, maestro: tuple, maestro_v: tuple, age: float, horizons, flip: int = 0) -> np.ndarray:
        """Fly centres at age + h for each horizon h (s): angle advanced at the measured rate (its sign follows the
        Maestro's facing: the formation is its child and Rotate turns in local space) from where the fly is now,
        radius from the age schedule, centre the Maestro moved at its current velocity."""
        cx, cy = maestro[0] + self.center_off[0], maestro[1] + self.center_off[1]
        th = math.atan2(tiny[1] - cy, tiny[0] - cx)
        out = np.empty((len(horizons), 2))
        for i, h in enumerate(horizons):
            a = th + math.radians(self.omega_deg_s[1 if flip else 0]) * h
            r = self.radius(age + h)
            x = cx + maestro_v[0] * h + r * math.cos(a)
            y = cy + maestro_v[1] * h + r * math.sin(a)
            out[i] = (min(max(x, self.bounds[0]), self.bounds[1]), min(max(y, self.bounds[2]), self.bounds[3]))
        return out
