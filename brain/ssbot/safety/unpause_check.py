"""Frozen-state check before an unpause (DESIGN §3.7.5 "rules for unpausing", used by Q5 / Q7 self-checks, P1, an
accidental pause, a false watchdog, and the greyed-Quit "unpause, evade, pause again" path).

    snap = FrozenState(hero_box=(x0, y0, x1, y1), hero_vel=(vx, vy))      # the last WorldState before the pause
    v = check_unpause(snap, tubes=forecast.reaches)                       # tubes(box, t0, t1) -> bool
    resume_decision(h, v.ok, quit_available)                              # RESUME / QUIT / STAY_ALERT

Rules:
- the world resumes exactly where it stopped; the check uses the last WorldState saved before the pause;
- HeroController.Pause() calls JumpReleased() (m0:N18): the hero's path is predicted with the jump released, and a
  cached plan may not assume the jump goes on;
- unpause only if no in-support threat tube reaches the knockback-inflated hurtbox within
  0.3 s (lockout) + L (input latency) + 0.1 s + the HideMenu fade, the time during which the hero cannot react; the
  fade was measured at 12 frames (0.20 s, acceptingInput false after a Cancel unpause, human session 20260930_210337
  frames 15238-15249 and 155823-155834); pausable again 18-19 frames (0.32 s) after the unpause;
- unpause with Continue + Submit, never Esc (pause_quit.PauseQuit.request_unpause);
- the 0.3 s real time after the unpause counts as unpausable in I1 / I3 and S(c): unpause_zone() gives that commit
  zone;
- Q5 resumes only with h >= 3 and the check passing; otherwise quit if the Quit item is available, else stay paused
  and alert.

The tube query is a callable so this module stays geometry-free: combat/forecast (W3) supplies it, kinematics (W1) can
supply a better hero sweep than the conservative default below.
"""
from collections.abc import Callable
from dataclasses import dataclass

from ssbot.safety.invariants import CommitZone

Box = tuple[float, float, float, float]          # x0, y0, x1, y1 (world units)
TubeQuery = Callable[[Box, float, float], bool]   # any in-support tube meets box during [t0, t1] s after the unpause
HeroSweep = Callable[[float, float], Box]         # hero hurtbox swept over [t0, t1] s after the unpause, jump released

MAX_FALL_VELOCITY = 30.0           # u/s (docs/facts/1.0.30000/hero_constants.json)
MAX_FALL_VELOCITY_WEIGHTED = 38.0  # with Weighted Belt
HIDE_MENU_S = 0.20           # measured (see the module docstring)
INFLATE_U = 0.15             # base margin (§3.5.3 m = 0.15 u + ...)

RESUME, QUIT, STAY_ALERT = "RESUME", "QUIT", "STAY_ALERT"


@dataclass(slots=True, frozen=True)
class FrozenState:
    hero_box: Box                     # hurtbox at the pause (HeroBox sizes, m0 §2.5)
    hero_vel: tuple[float, float] = (0.0, 0.0)
    weighted_belt: bool = False       # audited: changes the fall speed


@dataclass(slots=True, frozen=True)
class UnpauseTiming:
    lockout_s: float = 0.3            # m0:C12
    input_latency_s: float = 0.05     # L on the active input path
    margin_s: float = 0.1
    hide_menu_s: float = HIDE_MENU_S

    @property
    def horizon_s(self) -> float:
        return self.lockout_s + self.input_latency_s + self.margin_s + self.hide_menu_s


@dataclass(slots=True, frozen=True)
class UnpauseVerdict:
    ok: bool
    horizon_s: float
    first_reach_s: float | None = None
    reason: str = ""


def default_sweep(s: FrozenState) -> HeroSweep:
    """Conservative hero sweep without a kinematics model: horizontal drift at the frozen speed both ways, rising at
    the frozen upward speed (the jump release may cut it, not assumed), falling at the maximum fall speed."""
    x0, y0, x1, y1 = s.hero_box
    vx, vy = s.hero_vel
    fall = MAX_FALL_VELOCITY_WEIGHTED if s.weighted_belt else MAX_FALL_VELOCITY

    def sweep(t0: float, t1: float) -> Box:   # everything reachable over [0, t1] (covers [t0, t1])
        dx = abs(vx) * t1
        return x0 - dx, y0 - fall * t1, x1 + dx, y1 + max(vy, 0.0) * t1

    return sweep


def inflate(b: Box, m: float) -> Box:
    return b[0] - m, b[1] - m, b[2] + m, b[3] + m


def check_unpause(s: FrozenState, tubes: TubeQuery, timing: UnpauseTiming | None = None,
                  sweep: HeroSweep | None = None, inflate_u: float = INFLATE_U, slice_s: float = 1 / 30
                  ) -> UnpauseVerdict:
    """No in-support tube may reach the inflated, swept hurtbox anywhere in the horizon (checked in slices so a tube
    that passes before the hero drifts into its path is not missed nor over-counted)."""
    timing = timing or UnpauseTiming()
    sweep = sweep or default_sweep(s)
    horizon = timing.horizon_s
    n = max(1, int(round(horizon / slice_s)))
    for i in range(n):
        t0, t1 = horizon * i / n, horizon * (i + 1) / n
        if tubes(inflate(sweep(t0, t1), inflate_u), t0, t1):
            return UnpauseVerdict(False, horizon, t0, f"a support tube reaches the hero {t0:.2f}-{t1:.2f} s after "
                                                      "the unpause")
    return UnpauseVerdict(True, horizon)


def resume_decision(h: int, check_ok: bool, quit_available: bool, min_h: int = 3) -> str:
    """Q5 / Q7 self-check outcome (§3.7.4)."""
    if h >= min_h and check_ok:
        return RESUME
    if quit_available:
        return QUIT
    return STAY_ALERT


def unpause_zone(scene: str, timing: UnpauseTiming | None = None) -> CommitZone:
    """The 0.3 s after an unpause as an I3 commit zone (unpausable in I1 / I3 and S(c))."""
    timing = timing or UnpauseTiming()
    return CommitZone(key=f"{scene}:unpause_lockout", kind="unpause_lockout", unquittable_s=timing.lockout_s)
