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
sigma from the view's position noise). A detection that leaves the model by more than DEV_U (a bell the model does
not describe) withdraws the estimate: the bell's self template (the logged union) stands again.

The hero's own hits (task V review, 2026-10-03; M2 plan: "a known-effect action must not enlarge the danger zone").
The view has no tink event (drop bells have no HealthManager), but the tink's effect is the FSM's rule
(pogo_targets.tink: a side slash sends the bell away from the hitter at 5-10 u/s and its bounce that way, a down
spike clamps vy; 95 of 95 tinks of live run 20261002_171806 went the hero's facing). So when the hero attacks within
reach of a bell (TOUCH_BOX), the bell keeps exact paths: the untouched ones and one tinked branch per possible tink
step (every TINK_EVERY physics steps of the attack's frames in reach, the forecaster's time slack covering the steps
between), the side from the hero's facing (a down spike: vy clamped). Each detection after the touch prunes the
branches it leaves (beyond CONFIRM_U or 3 sigma); the bell is withdrawn only when none is left or there are more than
MAX_BRANCHES (a second attack multiplies them). Before, any touch withdrew the path until the track ruled a tink out:
the bell's whole self template stood instead (10 % of the drop-bell frames of degraded_dust run 20261002_224934,
about 1.8 drops a fight), so hitting a bell enlarged the danger zone, and the planner, which did not model its own hit
on a bell in this view, never chose to (0.4 redirects a phase-2 fight against the oracle view's 2.49).

Only detections count (visible_frac > 0: the noise model's coasting tracks and the filter's memory tracks do not), in
game time, each at the WorldState it came in (k frames late on the simulated final path): the forecast's origin is that
same WorldState, so no correction for the delay is needed.
"""
import math
import os
from dataclasses import dataclass, replace

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
# A touched bell gets its path back once the track shows no tink: CONFIRM_S after the last touch, every detection since
# the first touch within CONFIRM_U (or 3 sigma) of the untouched model, and no tink the track could not tell apart: a
# side slash facing the way the bell already moves (TINK RIGHT on a bell moving right at 4 u/s sets 5 u/s: 1 u/s, under
# the noise for a long time). A tink leaves the model fast otherwise: a falling bell (vx 0) goes to 5 or 10 u/s, a
# rising one stops (TINK DOWN), a bell moving left tinked left goes to -10, against the hitter to the other side.
# SSBOT_TOUCH_CONFIRM=0: a touched bell stays withdrawn (the A/B before).
CONFIRM_S = 0.25
CONFIRM_U = 0.35
CONFIRM_N = 6
TOUCH_CONFIRM = os.environ.get("SSBOT_TOUCH_CONFIRM", "1") != "0"
# tink branches instead of withdrawing a touched bell (SSBOT_TINK_BRANCHES=0: the withdrawal, the A/B before)
TINK_BRANCHES = os.environ.get("SSBOT_TINK_BRANCHES", "1") != "0"
TINK_EVERY = 2               # a tink hypothesis every this many physics steps (0.04 s; VE_DET_SLACK_S +-0.02 between)
TOUCH_GAP_S = 0.1            # touch frames this far apart are separate attacks
MAX_BRANCHES = 48
# ... or once the mean x offset of the detections after its first tink step is this many sigma of that mean off it
# (and MEAN_MIN_U): a tink late in the fall moves the bell 0.8 u off the untouched side and keeps it there, under
# the two-detections test; the column x comes from the same detector, so a bias shared by its detections cancels
MEAN_Z = 6.0
MEAN_MIN_U = 0.25
MEAN_MIN_N = 6
PATH_T_S = 4.0               # cached relative paths reach this far after the drop (a drop lives about 2 s)


@dataclass(slots=True)
class DropEstimate:
    x: float               # fall column
    t_drop: float          # game s of the drop (the fall's start state)
    side: int              # +1 / -1 decided, 0 open (both branches)
    n: int                 # fall detections used
    sx: float              # 1 sigma of x
    t_contact: float       # predicted first floor contact (game s)
    branches: tuple = ()   # touched: the paths still possible, (side, ((physics step of a tink, dir), ...)); ()
    #                        untouched: the bounce sides (side, or both)

    def paths(self) -> tuple:
        """(side, tinks) of every path the bell may be on."""
        if self.branches:
            return self.branches
        return ((self.side, ()),) if self.side else ((1, ()), (-1, ()))


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
        # touched bell -> [(game s, hero facing, the side tink's dir: the facing)]
        self.touch_log: dict[int, list[tuple[float, float, int]]] = {}
        self._memo: dict[int, tuple] = {}         # touched bell -> ((detections, touches), _branch_set result)
        self.t = 0.0
        if not hasattr(self, "_rel"):
            self._rel: dict = {}

    def rel_path(self, side: int, tinks: tuple) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """The path from the drop (x relative to the column, y, determined) on the physics-step grid up to PATH_T_S,
        bounce side `side` (0: open), tinks ((step, dir), ...): pogo_targets.simulate, cached per branch (it does not
        depend on the column x)."""
        key = (side, tinks)
        r = self._rel.get(key)
        if r is None:
            if len(self._rel) > 20000:
                self._rel.clear()
            ts = np.arange(int(PATH_T_S / STEP_S) + 1) * STEP_S
            reds = tuple((k * STEP_S - 1e-9, d) for k, d in tinks) or None
            r = self._rel[key] = simulate(self.spec, 0.0, self.y0, self.vx0, self.vy0, 0, None, ts, side=side,
                                          redirect=reds)
        return r

    def path_at(self, x: float, side: int, tinks: tuple, tau: np.ndarray
                ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Centre (x, y) and determined at tau s after the drop on one branch (rel_path, interpolated as simulate
        samples its own steps)."""
        rx, ry, rok = self.rel_path(side, tinks)
        ts = np.arange(len(rx)) * STEP_S
        tau = np.asarray(tau, np.float64)
        ok = np.interp(tau, ts, rok.astype(np.float64)) >= 1.0
        return x + np.interp(tau, ts, rx), np.interp(tau, ts, ry), ok & (tau <= ts[-1])

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
                self.touch_log.pop(e.id, None)
                self._memo.pop(e.id, None)
            x, y = e.pos.v
            s = e.pos.sigma if math.isfinite(e.pos.sigma) else 1.0
            lst.append((t, float(x), float(y), max(float(s), MIN_SIGMA_U)))
            self.type_of[e.id] = tk
            if attacking:
                # the hero's own attack may have met it (a tink: a side slash sends it away, a down attack clamps
                # its fall): the union of the hero's slash, up-slash and down-spike boxes (planner SIDE / UP / DOWN,
                # facing frame) grown by the bell's radius
                dx, dy = face * (float(x) - hx), float(y) - hy
                g = self.spec.r + TOUCH_MARGIN_U
                if TOUCH_BOX[0] - g <= dx <= TOUCH_BOX[1] + g and TOUCH_BOX[2] - g <= dy <= TOUCH_BOX[3] + g:
                    self.touched.add(e.id)
                    self.touch_log.setdefault(e.id, []).append((t, face, int(face)))
        for iid in [i for i, v in self.obs.items() if not v or t - v[-1][0] > GAP_S]:
            del self.obs[iid]
            self.type_of.pop(iid, None)
            self.touched.discard(iid)
            self.touch_log.pop(iid, None)
            self._memo.pop(iid, None)

    def _tau(self, y: np.ndarray) -> np.ndarray:
        """Time since the drop at height y on the fall: the 50 Hz semi-implicit steps as a parabola,
        y = y0 + (vy0 - g dt / 2) tau - g tau^2 / 2."""
        g = self.spec.g
        b = -(self.vy0 - 0.5 * g * STEP_S)
        d = np.maximum(b * b + 2.0 * g * (self.y0 - y), 0.0)
        return np.maximum((-b + np.sqrt(d)) / g, 0.0)

    def estimate(self, iid: int) -> DropEstimate | None:
        """The drop bell iid's drop, or None: no detection of its fall, or the track left the model. A bell the hero's
        attack may have tinked carries the branches still possible (_branches; TINK_BRANCHES off: None until the track
        rules a tink out, CONFIRM_S ...)."""
        if not self.ok:
            return None
        if iid not in self.touched:
            return self._estimate(iid)
        if TINK_BRANCHES:
            return self._touched(iid)
        if not TOUCH_CONFIRM:
            return None
        log = self.touch_log.get(iid) or []
        if not log or self.t - log[-1][0] < CONFIRM_S:
            return None
        est = self._estimate(iid)
        if est is None:
            return None
        a = np.asarray(self.obs.get(iid) or (), np.float64)
        if not len(a):
            return None
        post = a[a[:, 0] >= log[0][0]]
        if int((post[:, 0] > log[-1][0]).sum()) < CONFIRM_N:
            return None
        sides = (est.side,) if est.side else (1, -1)
        lim = np.maximum(CONFIRM_U, 3.0 * post[:, 3]) + SKIN_Z * est.sx
        ts = np.maximum(post[:, 0] - est.t_drop, 0.0)
        dmin = np.full(len(post), np.inf)
        for sd in sides:
            for dt in DEV_DT_S:
                cx, cy, _ = simulate(self.spec, est.x, self.y0, self.vx0, self.vy0, 0, None,
                                     np.concatenate([[0.0], np.maximum(ts + dt, 0.0)]), side=sd)
                dmin = np.minimum(dmin, np.hypot(cx[1:] - post[:, 1], cy[1:] - post[:, 2]))
        if (dmin > lim).any():
            return None
        # a side slash facing the way the model has the bell moving: TINK RIGHT on a bell going right at 4 u/s
        # (5 u/s) cannot be told apart yet, so the path is not given back
        th = np.array([u for u, *_ in log]) - est.t_drop
        for sd in sides:
            cx, _, _ = simulate(self.spec, est.x, self.y0, self.vx0, self.vy0, 0, None,
                                np.concatenate([np.maximum(th, 0.0), np.maximum(th, 0.0) + STEP_S]), side=sd)
            vx = (cx[len(th):] - cx[:len(th)]) / STEP_S
            if any(face > 0 and v > 0.5 for (_, face, _d), v in zip(log, vx)):
                return None
        self.touched.discard(iid)          # untouched after all: later attacks start a new check
        self.touch_log.pop(iid, None)
        return est

    def _touched(self, iid: int) -> DropEstimate | None:
        """A bell the hero's attack may have tinked: the drop from the detections before the first touch, and the
        branches (untouched, tinked at each possible step) the detections since then still allow. Once no tinked
        branch is left and the last touch is CONFIRM_S old, the bell counts as untouched again."""
        log = self.touch_log.get(iid) or []
        if not log:
            return self._estimate(iid)
        # the branches change only with a new detection or touch (the forecaster asks every tick, sometimes twice)
        key = (len(self.obs.get(iid) or ()), len(log))
        memo = self._memo.get(iid)
        if memo is None or memo[0] != key:
            memo = self._memo[iid] = (key, self._branch_set(iid, log))
        if memo[1] is None:
            return None
        est, branches = replace(memo[1][0]), memo[1][1]
        if self.t - log[-1][0] >= CONFIRM_S and all(not tk for _, tk in branches):
            self.touched.discard(iid)              # untouched after all: later attacks start a new check
            self.touch_log.pop(iid, None)
            self._memo.pop(iid, None)
            sides = {sd for sd, _ in branches}
            est.side = next(iter(sides)) if len(sides) == 1 else 0
            return est
        est.branches = tuple(sorted(branches))
        return est

    def _branch_set(self, iid: int, log: list) -> tuple | None:
        """(the drop from the detections before the first touch, the branches the later detections allow) or None."""
        est = self._estimate(iid, before=log[0][0])
        if est is None:
            return None
        a = np.asarray(self.obs.get(iid) or (), np.float64)
        post = a[a[:, 0] >= log[0][0]] if len(a) else a
        # a branch goes once two detections leave it by DEV_U / DEV_Z sigma (the withdrawal's test): a true branch is
        # never pruned by noise (5 sigma, twice), a wrong tink leaves within 0.1-0.2 s (5-10 u/s off)
        lim = (np.maximum(DEV_U, DEV_Z * post[:, 3]) + SKIN_Z * est.sx) if len(post) else post
        tau_c = est.t_contact - est.t_drop
        b0 = self.spec.bounces[0] if self.spec.bounces else {}
        tau_apex = tau_c + float(b0.get("vy", 0.0)) / self.spec.g if self.spec.g > 0 else tau_c
        branches = {(sd, ()) for sd in ((est.side,) if est.side else (1, -1))}
        # touch frames grouped into attacks; each attack may tink once at any of its steps (a second one multiplies)
        groups: list[list[tuple]] = []
        for row in log:
            if groups and row[0] - groups[-1][-1][0] <= TOUCH_GAP_S and row[2] == groups[-1][-1][2]:
                groups[-1].append(row)
            else:
                groups.append([row])
        for gi, grp in enumerate(groups):
            k0 = int(math.floor((grp[0][0] - est.t_drop) / STEP_S)) - 1
            k1 = int(math.ceil((grp[-1][0] - est.t_drop) / STEP_S)) + 1
            steps = list(range(max(k0, 0), k1 + 1, TINK_EVERY))
            if steps and steps[-1] < k1:
                steps.append(k1)
            new = set(branches)
            # the view does not tell a side slash from an up-slash (no tink) or a down spike (TINK DOWN): all three
            for d in (grp[0][2], 0):
                for sd, tk in branches:
                    for k in steps:
                        if tk and k <= tk[-1][0]:
                            continue
                        if d == 0 and not tau_c < k * STEP_S < tau_apex:
                            continue                        # TINK DOWN changes only a rising bell (vy <= 0)
                        s2 = d if d and k * STEP_S <= tau_c else sd     # tinked before the bounce: its side is d
                        new.add((s2, tk + ((k, d),)))
            if len(new) > MAX_BRANCHES:
                return None
            # the detections up to the next attack prune them
            t_next = groups[gi + 1][0][0] if gi + 1 < len(groups) else math.inf
            sel = post[:, 0] < t_next if len(post) else np.zeros(0, bool)
            branches = {b for b in new if self._fits(est, b, post[sel], lim[sel])}
            if not branches:
                return None
        return est, branches

    def _fits(self, est: DropEstimate, branch: tuple, rows: np.ndarray, lim: np.ndarray) -> bool:
        """At most one detection in rows beyond lim of the branch's path (at the closest of DEV_DT_S, the step's
        phase), and the detections since its first tink step (the untouched: since the touch) not off it on average
        (MEAN_Z)."""
        if not len(rows):
            return True
        tau = rows[:, 0] - est.t_drop
        dmin = np.full(len(rows), np.inf)
        k0 = branch[1][0][0] * STEP_S if branch[1] else -math.inf
        aft = tau >= k0
        n = int(aft.sum())
        m_min = math.inf
        for dt in DEV_DT_S:
            cx, cy, _ = self.path_at(est.x, branch[0], branch[1], np.maximum(tau + dt, 0.0))
            dmin = np.minimum(dmin, np.hypot(cx - rows[:, 1], cy - rows[:, 2]))
            if n >= MEAN_MIN_N:
                m_min = min(m_min, abs(float(np.mean(cx[aft] - rows[aft, 1]))))
        if int((dmin > lim).sum()) >= 2:
            return False
        if n >= MEAN_MIN_N:
            sm = math.sqrt(float(np.mean(rows[aft, 3] ** 2)) / n + est.sx ** 2)
            if m_min > max(MEAN_MIN_U, MEAN_Z * sm):
                return False
        return True

    def _estimate(self, iid: int, before: float | None = None) -> DropEstimate | None:
        o = self.obs.get(iid)
        if not o:
            return None
        a = np.asarray(o, np.float64)
        if before is not None:
            a = a[a[:, 0] < before]
            if not len(a):
                return None
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


# ---- attack bells -----------------------------------------------------------------------------------------------
#
# A burst throws two attack bells (live run 20261002_171806 i0_000: 100 launches, 50 per type key): each is drawn from
# its Launch frame (100 of 100), at y 0.954 and x = the burst's transform x -2.0 (AtkBell L) / +2.0 (R) whatever the
# boss's flip, with velocity (-1, 38) / (+1, 38); from that first frame the registry physics (pogo_targets.simulate:
# rise and fall at g 66, first floor contact at y 2.9635 -> vx 12 the same way, vy 14 at every later floor contact)
# matches the logged centre within 0.0004 u over its whole life (it passes through the arena walls: x 61.5-109.2), and
# its collider goes off 0.80-2.02 s after the first floor contact (End Timer 2 s; earlier when the fight ended). No
# tink state: a hero hit does not change its path (a down spike only disarms it 0.5 s, DamageHero cooldown).
# So vision fixes the path from three numbers: the launch time (each detection's height inverted on the known rise /
# fall curve, robust median), the launch x (the detections moved back along vx), and the side, which is the bell's
# place in its pair (the left one goes left, 4.0 u apart) or its place against the burst anchor (-2 / +2), else the
# drift of x (1 u/s) once significant; until then both sides.

ATK_BELL = "BoneBeast AtkBell"
ATK_LIFE_SLACK_S = 0.04      # the End Timer counts frames: 2.02 s logged at most
ATK_PAIR_DT_S = 0.05         # two launches this close in time ...
ATK_PAIR_DX_U = (3.4, 4.6)   # ... and this far apart: one burst's pair (4.0 u)
ATK_ANCHOR_DX_U = (1.4, 2.6)  # a launch this far from the burst anchor: its side (2.0 u)
ATK_KEEP_S = 0.25            # an estimate is kept this long past its collider's end


@dataclass(slots=True)
class LaunchEstimate:
    iid: int
    xm: float               # mean x of the launch-arc detections ...
    taum: float             # ... and their mean time since the launch: launch x = xm - side * vx * taum
    t_launch: float         # game s of the Launch frame
    side: int               # +1 / -1 decided, 0 open (both branches)
    n: int
    sx: float               # 1 sigma of x0
    t_end: float            # collider off (the End Timer after the first floor contact), game s
    pair: bool = False      # its burst partner is on an exact path too


class AtkBellTracks:
    """Detections of attack bells per entity id and the launch each one is on (LaunchEstimate). An estimate outlives
    its detections (a bell off-screen still follows its path) until its collider's end, and is withdrawn when the
    latest detections leave its model."""

    def __init__(self, spec: TargetSpec):
        self.spec = spec
        st = spec.start or {}
        self.y0 = float(st.get("y", math.nan))
        self.vx_mag = abs(float(st.get("vx", 0.0)))
        self.vy0 = float(st.get("vy", 0.0))
        self.ok = (math.isfinite(self.y0) and self.vy0 > 0 and spec.ground_y is not None and bool(spec.bounces)
                   and spec.life_after_first_s is not None)
        self.t_bounce = math.nan          # first floor contact after the launch (registry physics, 50 Hz steps)
        if self.ok:
            y, vy, k = self.y0, self.vy0, 0
            while k < 1000 and not (y <= spec.ground_y and vy < 0):
                vy -= spec.g * STEP_S
                y += vy * STEP_S
                k += 1
            self.t_bounce = k * STEP_S
            self.ok = k < 1000
        self.reset()

    def reset(self) -> None:
        self.obs: dict[int, list[tuple[float, float, float, float]]] = {}
        self.type_of: dict[int, str] = {}
        self.est: dict[int, LaunchEstimate] = {}       # current launch per id (kept past the detections)
        self.old: list[LaunchEstimate] = []            # earlier launches of re-used ids, until their end
        self.t = 0.0
        if not hasattr(self, "_rel"):
            self._rel: dict = {}

    def update(self, ws: WorldState, t: float, anchor_x: float | None = None) -> None:
        """Add this frame's attack-bell detections; anchor_x: the current burst's anchor (its transform x), if known."""
        self.t = t
        if not self.ok:
            return
        seen = set()
        for e in ws.entities:
            tk = e.type_key.v
            if not tk.startswith(ATK_BELL) or e.hidden or e.visible_frac <= 0.0 or e.pos.conf <= 0.0:
                continue
            lst = self.obs.setdefault(e.id, [])
            if lst and t - lst[-1][0] > GAP_S:
                lst.clear()                 # undrawn a while: a new launch of the same object
                old = self.est.pop(e.id, None)
                if old is not None:
                    self.old.append(old)
            x, y = e.pos.v
            s = e.pos.sigma if math.isfinite(e.pos.sigma) else 1.0
            lst.append((t, float(x), float(y), max(float(s), MIN_SIGMA_U)))
            self.type_of[e.id] = tk
            seen.add(e.id)
        for iid in seen:
            est = self._estimate(iid, anchor_x)
            if est is None:
                self.est.pop(iid, None)
            else:
                self.est[iid] = est
        self._pairs()
        for iid in [i for i, v in self.obs.items() if (not v or t - v[-1][0] > GAP_S) and i not in self.est]:
            del self.obs[iid]
            self.type_of.pop(iid, None)
        for iid in [i for i, e in self.est.items() if t > e.t_end + ATK_KEEP_S]:
            del self.est[iid]
            self.obs.pop(iid, None)
            self.type_of.pop(iid, None)
        self.old = [e for e in self.old if t <= e.t_end + ATK_KEEP_S]

    def estimates(self) -> list[LaunchEstimate]:
        return list(self.est.values()) + self.old

    def _pairs(self) -> None:
        """A burst's two launches: their sides from their order, and both marked paired."""
        ests = self.estimates()
        for e in ests:
            e.pair = False
        for i, a in enumerate(ests):
            for b in ests[i + 1:]:
                if abs(a.t_launch - b.t_launch) > ATK_PAIR_DT_S:
                    continue
                for left, right in ((a, b), (b, a)):
                    d = self.x0(right, 1) - self.x0(left, -1)
                    if ATK_PAIR_DX_U[0] <= d <= ATK_PAIR_DX_U[1]:
                        left.pair = right.pair = True
                        left.side, right.side = -1, 1
                        break

    def _tau(self, y: float, rising: bool) -> float:
        """Time since the launch at height y on the rise (or the fall) before the first floor contact:
        y = y0 + (vy0 - g dt / 2) tau - g tau^2 / 2 (50 Hz semi-implicit steps as a parabola)."""
        g = self.spec.g
        a = self.vy0 - 0.5 * g * STEP_S
        d = max(a * a - 2.0 * g * (y - self.y0), 0.0)
        return (a - math.sqrt(d)) / g if rising else (a + math.sqrt(d)) / g

    def _estimate(self, iid: int, anchor_x: float | None) -> LaunchEstimate | None:
        o = self.obs.get(iid)
        if not o:
            return None
        a = np.asarray(o, np.float64)
        t, x, y, s = a[:, 0], a[:, 1], a[:, 2], a[:, 3]
        # launch time: the first detection on the rise or on the fall, whichever explains the others better (each
        # detection's height inverted on the branch nearest to that guess)
        best = None
        for rising in (True, False):
            tl0 = t[0] - self._tau(float(y[0]), rising) - STEP_BIAS_S
            tau = np.empty(len(t))
            for i in range(len(t)):
                if t[i] - tl0 >= self.t_bounce - STEP_S:
                    tau[i] = np.nan             # past the first floor contact: not on the launch arc
                    continue
                r, f = self._tau(float(y[i]), True), self._tau(float(y[i]), False)
                tau[i] = r if abs(r - (t[i] - tl0)) <= abs(f - (t[i] - tl0)) else f
            ok = np.isfinite(tau)
            if not ok.any():
                continue
            tl = float(np.median(t[ok] - tau[ok])) - STEP_BIAS_S
            err = float(np.median(np.abs(t[ok] - tau[ok] - STEP_BIAS_S - tl)))
            if best is None or err < best[0]:
                best = (err, tl)
        if best is None:
            return None
        tl = best[1]
        arc = (t - tl) < self.t_bounce - STEP_S
        if not arc.any():
            return None
        tau = np.maximum(t[arc] - tl, 0.0)
        n = int(arc.sum())
        sig = float(np.sqrt(np.mean(s[arc] ** 2)))
        sx = sig / math.sqrt(n)
        prev = self.est.get(iid)
        side = prev.side if prev is not None and prev.pair else 0
        if not side and anchor_x is not None:
            xm = float(np.mean(x[arc]))
            d = xm - anchor_x
            if ATK_ANCHOR_DX_U[0] <= abs(d) <= ATK_ANCHOR_DX_U[1] + self.vx_mag * float(tau.mean()):
                side = 1 if d > 0 else -1
        if not side and n >= 3:
            # the drift of x along the launch arc (vx_mag u/s)
            den = float(((tau - tau.mean()) ** 2).sum())
            if den > 1e-9:
                slope = float(((tau - tau.mean()) * (x[arc] - x[arc].mean())).sum()) / den
                if abs(slope) > SIDE_Z * sig / math.sqrt(den) and abs(slope) > SIDE_MIN_FRAC * self.vx_mag:
                    side = 1 if slope > 0 else -1
        sides = (side,) if side else (1, -1)
        xm, taum = float(np.mean(x[arc])), float(np.mean(tau))
        x0s = {sd: xm - sd * self.vx_mag * taum for sd in sides}
        if not side:
            # after the first floor contact the side shows at 12 u/s at once
            aft = ~arc
            if aft.any():
                errs = {sd: float(np.min(np.hypot(*self._dev(x0s[sd], sd, tl, a[aft])))) for sd in sides}
                lim = max(DEV_U, DEV_Z * float(s[aft].max())) + SKIN_Z * sx
                good = [sd for sd in sides if errs[sd] <= lim]
                if len(good) == 1:
                    side = good[0]
                    sides = (side,)
        t_end = tl + self.t_bounce + float(self.spec.life_after_first_s) + ATK_LIFE_SLACK_S
        # the model must still describe the latest detections
        last = a[-2:]
        dmin = np.full(len(last), np.inf)
        for sd in sides:
            for dt in DEV_DT_S:
                dx, dy = self._dev(x0s[sd], sd, tl + dt, last)
                dmin = np.minimum(dmin, np.hypot(dx, dy))
        dev_lim = np.maximum(DEV_U, DEV_Z * last[:, 3])
        if (dmin > dev_lim + SKIN_Z * sx).all():
            return None
        return LaunchEstimate(iid, xm, taum, tl, side, n, sx, t_end, prev.pair if prev is not None else False)

    def path_at(self, x0: float, side: int, tinks: tuple, tau: np.ndarray
                ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Centre (x, y) and determined at tau s after the launch from x0 on that side (no tinks: an attack bell has
        no Tink state), from the launch path relative to x0, cached per side on the physics-step grid (as
        DropBellTracks.path_at; the forecaster applies the collider's life)."""
        r = self._rel.get(side)
        if r is None:
            ts = np.arange(int(PATH_T_S / STEP_S) + 1) * STEP_S
            r = self._rel[side] = simulate(self.spec, 0.0, self.y0, side * self.vx_mag, self.vy0, 0, None, ts)
        rx, ry, rok = r
        ts = np.arange(len(rx)) * STEP_S
        tau = np.asarray(tau, np.float64)
        ok = np.interp(tau, ts, rok.astype(np.float64)) >= 1.0
        return x0 + np.interp(tau, ts, rx), np.interp(tau, ts, ry), ok & (tau <= ts[-1])

    t_fall = math.inf        # (no random bounce to redirect: the forecaster's redirect rule never applies)

    def x0(self, e: LaunchEstimate, side: int) -> float:
        """The launch x on that side."""
        return e.xm - side * self.vx_mag * e.taum

    def path_args(self, e: LaunchEstimate, side: int) -> tuple[float, float, float, float]:
        """(x, y, vx, vy) at the launch for simulate() on that side."""
        return self.x0(e, side), self.y0, side * self.vx_mag, self.vy0

    def _dev(self, x0: float, side: int, tl: float, rows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        tau = np.maximum(rows[:, 0] - tl, 0.0)
        cx, cy, _ = simulate(self.spec, x0, self.y0, side * self.vx_mag, self.vy0, 0, None,
                             np.concatenate([[0.0], tau]))
        return cx[1:] - rows[:, 1], cy[1:] - rows[:, 2]
