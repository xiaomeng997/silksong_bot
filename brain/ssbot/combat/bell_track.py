"""Drop-bell paths from what vision sees (task V, DESIGN §3.9.2 the vision-equivalent view): the exact two-branch
support of a falling drop bell without its FSM state or its logged velocity.

Why. In the oracle view a falling drop bell is support along its exact path (pogo_targets.simulate from the logged
position, velocity and FSM state; two branches for the random bounce side): live 6ab67e1 74 fights, 1 DropBell hit.
The vision view had only the bell's self template (the logged union of every fall and both bounce sides, placed from
the ceiling dust cue with its timing slack) until the bell was gone: degraded_dust run 20261002_173956, 19 of 28 hits
were DropBell M2 in phase 2, each after 45-60 frames of FORCED_RISK inside that union.

What vision has. A drop bell is drawn from the frame it starts to fall (live run 20261002_171806 i0_000: 178 of 178
drops first drawn in Air at the hang height y 13.74 with velocity (0, -17), registry `start`), falls straight down
(the FSM sets vx 0), bounces once off the floor (y 3.18) at +-4 u/s and vy 30 to a random side, and sinks through
the floor at its second contact (registry `bounces`). So its path is fixed by three numbers vision can read off the
track of its detections: the column x (the mean of the fall detections), the drop time (each fall detection's height
inverted on the known fall curve, robust median), and the bounce side (the sign of the x drift after the first contact,
open until it is significant). The path itself is then the registry physics from the drop (pogo_targets.simulate in
the game's 50 Hz steps, which start at the drop), sampled at (tk + time since the drop), with the forecaster's time
slack (DET_SLACK_S) and a contact skin grown by the column's x uncertainty (3 sigma of the mean of the detections,
sigma from the view's position noise). A detection that leaves the model by more than DEV_U (a side slash's tink, a
bell the model does not describe) withdraws the estimate: the bell's self template (the logged union) stands again;
so does the hero attacking within reach of it (a tink changes vx to 5-10 u/s, which the drift shows only slowly:
live 20261002_171806 i0 ep0, a DropBell M tinked to vx 5 in Bounce Air stayed within 0.42 u of the untouched model
for 8 frames).

Only detections count (visible_frac > 0: the noise model's coasting tracks and the filter's memory tracks do not), in
game time, each at the WorldState it came in (k frames late on the simulated final path): the forecast's origin is that
same WorldState, so no correction for the delay is needed.
"""
import math
from dataclasses import dataclass

import numpy as np

from ssbot.combat.pogo_targets import STEP_S, TargetSpec, simulate
from ssbot.core.worldstate import WorldState

DROP_BELL = "BoneBeast DropBell"
GAP_S = 0.5            # undrawn this long: the next sighting is a new drop of the same bell object
STEP_BIAS_S = 0.5 * STEP_S   # a frame shows the last physics step: a height read is on average half a step old
SIDE_Z = 5.0           # the bounce side is taken once the drift's slope is this many sigma from 0 ...
SIDE_MIN_FRAC = 0.5    # ... and at least this share of the registry's |vx|
SIDE_AFTER_S = 0.04    # detections this soon after the predicted contact are not used for the side
DEV_U = 0.6            # the last two detections this far from the model (or DEV_Z sigma) withdraw the estimate
DEV_Z = 5.0
DEV_DT_S = (-STEP_S, 0.0, STEP_S)    # ... at the closest of these time offsets (the physics step's phase)
SKIN_Z = 3.0           # the skin grows by this many sigma of the column's x
MIN_SIGMA_U = 0.02     # floor for a detection's sigma (an exact view reports 0)
# the hero attacking this close to a bell may have tinked it (the view has no tink event: drop bells have no
# HealthManager): the union of the Hunter slash / up-slash / down-spike boxes relative to the hurtbox centre in the
# facing frame (planner SIDE, UP, DOWN: x -1.23 .. 2.81, y -1.96 .. 3.33), grown by the bell's radius + this margin
ATTACK_MODES = frozenset(("attack", "pogo"))
TOUCH_BOX = (-1.23, 2.81, -1.96, 3.33)
TOUCH_MARGIN_U = 0.5


@dataclass(slots=True)
class DropEstimate:
    x: float               # fall column
    t_drop: float          # game s of the drop (the fall's start state)
    side: int              # +1 / -1 decided, 0 open (both branches)
    n: int                 # fall detections used
    sx: float              # 1 sigma of x
    t_contact: float       # predicted first floor contact (game s)


class DropBellTracks:
    """Detections of drop bells per entity id, and the drop each one is on (DropEstimate)."""

    def __init__(self, spec: TargetSpec):
        self.spec = spec
        st = spec.start or {}
        self.y0 = float(st.get("y", math.nan))
        self.vx0 = float(st.get("vx", 0.0))
        self.vy0 = float(st.get("vy", 0.0))
        self.ok = math.isfinite(self.y0) and spec.ground_y is not None and bool(spec.bounces)
        # the fall's floor contact time (registry physics from the start state)
        self.t_fall = math.nan
        self.vx_mag = 0.0
        if self.ok:
            ts = np.arange(0, 200) * STEP_S
            _, cy, _ = simulate(spec, 0.0, self.y0, self.vx0, self.vy0, 0, None, ts, side=1)
            low = np.flatnonzero(cy <= spec.ground_y + 1e-9)
            self.t_fall = float(ts[low[0]]) if len(low) else math.nan
            self.vx_mag = float(spec.bounces[0].get("vx_mag", 0.0))
            self.ok = math.isfinite(self.t_fall)
        self.reset()

    def reset(self) -> None:
        self.obs: dict[int, list[tuple[float, float, float, float]]] = {}
        self.type_of: dict[int, str] = {}
        self.touched: set[int] = set()
        self.t = 0.0

    def update(self, ws: WorldState, t: float) -> None:
        self.t = t
        h = ws.hero
        attacking = h.mode.v in ATTACK_MODES and h.pos.conf > 0
        face = 1.0 if h.facing.v >= 0 else -1.0
        hx, hy = h.pos.v
        for e in ws.entities:
            tk = e.type_key.v
            if not tk.startswith(DROP_BELL) or e.hidden or e.visible_frac <= 0.0 or e.pos.conf <= 0.0:
                continue
            lst = self.obs.setdefault(e.id, [])
            if lst and t - lst[-1][0] > GAP_S:
                lst.clear()
                self.touched.discard(e.id)
            x, y = e.pos.v
            s = e.pos.sigma if math.isfinite(e.pos.sigma) else 1.0
            lst.append((t, float(x), float(y), max(float(s), MIN_SIGMA_U)))
            self.type_of[e.id] = tk
            if attacking:
                # the hero's own attack may have met it (a tink: a side slash sends it away, a down attack clamps
                # its fall), which no estimate here models: the union of the hero's slash, up-slash and down-spike
                # boxes (planner SIDE / UP / DOWN, facing frame) grown by the bell's radius
                dx, dy = face * (float(x) - hx), float(y) - hy
                g = self.spec.r + TOUCH_MARGIN_U
                if TOUCH_BOX[0] - g <= dx <= TOUCH_BOX[1] + g and TOUCH_BOX[2] - g <= dy <= TOUCH_BOX[3] + g:
                    self.touched.add(e.id)
        for iid in [i for i, v in self.obs.items() if not v or t - v[-1][0] > GAP_S]:
            del self.obs[iid]
            self.type_of.pop(iid, None)
            self.touched.discard(iid)

    def _tau(self, y: np.ndarray) -> np.ndarray:
        """Time since the drop at height y on the fall: the 50 Hz semi-implicit steps as a parabola,
        y = y0 + (vy0 - g dt / 2) tau - g tau^2 / 2."""
        g = self.spec.g
        b = -(self.vy0 - 0.5 * g * STEP_S)
        d = np.maximum(b * b + 2.0 * g * (self.y0 - y), 0.0)
        return np.maximum((-b + np.sqrt(d)) / g, 0.0)

    def estimate(self, iid: int) -> DropEstimate | None:
        """The drop bell iid's drop, or None: no detection of its fall, or the track left the model."""
        if not self.ok or iid in self.touched:
            return None
        o = self.obs.get(iid)
        if not o:
            return None
        a = np.asarray(o, np.float64)
        t, x, y, s = a[:, 0], a[:, 1], a[:, 2], a[:, 3]
        if y[0] <= self.spec.ground_y + 0.5:
            return None              # first seen near the floor: not a fall we can time
        td0 = t[0] - self._tau(y[:1])[0] - STEP_BIAS_S
        fall = (t - td0) < self.t_fall - STEP_S
        if not fall.any():
            return None
        td = float(np.median(t[fall] - self._tau(y[fall]))) - STEP_BIAS_S
        fall = (t - td) < self.t_fall - STEP_S
        if not fall.any():
            return None
        n = int(fall.sum())
        xb = float(x[fall].mean())
        sig = float(np.sqrt(np.mean(s[fall] ** 2)))
        sx = sig / math.sqrt(n)
        tc = td + self.t_fall
        side = 0
        aft = t >= tc + SIDE_AFTER_S
        if aft.any():
            dt = t[aft] - tc
            dx = x[aft] - xb
            den = float((dt * dt).sum())
            slope = float((dx * dt).sum()) / den
            s_slope = math.sqrt(float(np.mean(s[aft] ** 2)) / den + sx * sx / max(float(dt.mean()) ** 2, 1e-6))
            if abs(slope) > SIDE_Z * s_slope and abs(slope) > SIDE_MIN_FRAC * self.vx_mag:
                side = 1 if slope > 0 else -1
        est = DropEstimate(xb, td, side, n, sx, tc)
        # the model must still describe the latest detections (a tink, or not a drop bell's fall)
        last = a[-2:]
        tau = last[:, 0] - td
        dev_lim = np.maximum(DEV_U, DEV_Z * last[:, 3])
        dmin = np.full(len(last), np.inf)
        for sd in ((side,) if side else (1, -1)):
            for dt in DEV_DT_S:
                cx, cy, _ = simulate(self.spec, xb, self.y0, self.vx0, self.vy0, 0, None,
                                     np.concatenate([[0.0], np.maximum(tau + dt, 0.0)]), side=sd)
                d = np.hypot(cx[1:] - last[:, 1], cy[1:] - last[:, 2])
                dmin = np.minimum(dmin, d)
        if (dmin > dev_lim + SKIN_Z * sx).all():
            return None
        return est
