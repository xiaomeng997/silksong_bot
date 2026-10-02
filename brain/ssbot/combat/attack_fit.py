"""Model-based tracking of a committed boss attack from vision observations (multi-frame fusion; the reference design
for the M3 vision tracker, DESIGN 3.2 track / phase_hmm). Consumes WorldState-level observations only.

    fit = AttackFit(model)
    fit.start(family, anchor, t_start_guess)        # the attack is known (dust cue + emergence, or the first frame)
    fit.observe(t, x, y)                            # every frame the boss is seen (noisy, 2-4 frames late)
    r = fit.result()                                # None (too few frames) or FitResult(t_start, dx, rms, ok)

Once the Bell Beast has committed to an attack its motion is the family's template: the logged mean path in the
attack's anchor frame (BossModel family path: x' mirrored, y; the anchors' paths spread < 0.6 u), started at an
unknown time. The unknowns, the start time offset and a small x offset of the anchor, are fitted by least squares over
every observation since the attack began, not the latest frame: the noise averages down with the frame count, so a
view that is 2-4 frames late still places the boss well along its path. The start time is searched on a 1/60 s grid
within +-max_dt_s of the guess, the x offset is closed-form (the mean residual) and bounded by max_dx_u. A fit whose
residual rms exceeds max_rms_u (or whose offset hits its bound) is rejected: the boss is not doing what the template
says, and the caller falls back to the broad support at once (anomaly).
"""
from dataclasses import dataclass

import numpy as np

from ssbot.combat.boss_model import Anchor, BossModel


@dataclass(slots=True)
class FitResult:
    t_start: float             # fitted attack start (game s)
    dx: float                  # fitted anchor x offset (u)
    rms: float                 # residual rms over the observations (u)
    n: int                     # observations used
    ok: bool                   # within the residual test


class AttackFit:
    def __init__(self, model: BossModel, max_dt_s: float = 0.15, max_dx_u: float = 1.5, max_rms_u: float = 0.6,
                 min_n: int = 4, step_s: float = 1 / 60):
        self.model = model
        self.max_dt_s, self.max_dx_u, self.max_rms_u, self.min_n, self.step_s = (max_dt_s, max_dx_u, max_rms_u,
                                                                                  min_n, step_s)
        self.reset()

    def reset(self) -> None:
        self.family: str | None = None
        self.anchor: Anchor | None = None
        self.t0: float | None = None
        self.obs: list[tuple[float, float, float]] = []
        self._last: FitResult | None = None

    def start(self, family: str, anchor: Anchor, t_start_guess: float) -> None:
        if (family, anchor, t_start_guess) == (self.family, self.anchor, self.t0):
            return
        self.reset()
        self.family, self.anchor, self.t0 = family, anchor, t_start_guess

    def observe(self, t: float, x: float, y: float) -> None:
        if self.family is not None:
            self.obs.append((t, x, y))
            self._last = None

    def _template(self, t_rel: np.ndarray) -> np.ndarray | None:
        f = self.model.families.get(self.family)
        if f is None or f.path is None:
            return None
        path = f.path
        return np.interp(t_rel, path[:, 0], path[:, 6], left=np.nan, right=np.nan)

    def result(self) -> FitResult | None:
        if self._last is not None:
            return self._last
        if self.family is None or self.anchor is None or len(self.obs) < self.min_n:
            return None
        o = np.asarray(self.obs)
        if self._template(np.zeros(1)) is None:
            return None
        m = self.anchor.mirror
        best = None
        for dt in np.arange(-self.max_dt_s, self.max_dt_s + 1e-9, self.step_s):
            ts = self.t0 + dt
            xm = self._template(o[:, 0] - ts)
            ok = np.isfinite(xm)
            if ok.sum() < self.min_n:
                continue
            pred = self.anchor.x + m * xm[ok]            # the template is the anchor frame's x' = m (x - anchor)
            res = o[ok, 1] - pred
            dx = float(np.clip(res.mean(), -self.max_dx_u, self.max_dx_u))
            rms = float(np.sqrt(np.mean((res - dx) ** 2)))
            if best is None or rms < best.rms:
                best = FitResult(float(ts), dx, rms, int(ok.sum()), True)
        if best is not None:
            best.ok = best.rms <= self.max_rms_u and abs(best.dx) < self.max_dx_u
        self._last = best
        return best
