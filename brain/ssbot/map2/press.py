"""Map v2 stage M4 S1: THE PRESS CHECK - a strike is credited only when the game would start it from her concrete kin
state at the press (LEAD NOTE 4 of C:\\ssbot\\data\\m2_play\\map2\\m4\\PROGRESS.txt; the airceil verifier's
verify\\stage3.txt 2.1 / 4.1; HANDOFF 'Task map2 - stage M4' / 'S1', forum.md 100).

The search found its presses in the envelope's clusters (their end-condition bits), whose lanes are not the witness's
concrete state, and simulate / strike.dslash_contact credited a down slash's contact from the geometry alone: 24.7 %
of the airceil recorded situations' plans had a press the game would not start (a down slash pressed with the
umbrella's jump released - the release closes it in the press frame and the attack is lost, kin's H2_REL_LOSS; in the
umbrella's antic / inflate; in the air sprint, where the press is queued and the sprint's Attack Cancel swings 1 - 3
frames later with the keys held then, a side slash once down is let go; a Clawline in the antic / inflate). Here:

- kin_trace: her kin rollout (kin_jit's own frame loop, nominal timing - search.World.roll's) recording per frame the
  state BEFORE the frame's Update (after its physics steps and events: what a press there meets) and the attack
  AFTER it; at the press frames also the same Update with kin's downspike lock lifted.
- ds_start: a down slash pressed at rollout index t starts at t' in t .. t + LOOK (the air sprint's Attack Cancel reads
  InputHandler's 0.1 s queue: M4a's max(AS + 4, press + 1)) when the kin state starts an attack there and it is a down
  slash ('down'); an attack that is not one ('side') and none at all ('none') are not credited; a press that only
  kin's downspike lock (BOUNCE / DS_REC, ~15 frames after a pogo onset) holds, FREE_MIN frames or more after that onset,
  is credited at t ('lock': the game's recovery is 9 - 11 frames, no down slash started < 10 frames after a pogo onset
  in 657 - the airceil verifier's dsrec_timing; the search's M0 cadence governs there).
- claw_ok: the Clawline press frame P - env_jit.claw_allowed's rule on her state before P's Update (airborne, normal
  control, the umbrella's float / deflate, with HERO2 H2_CLAW_SPR the air sprint - M4a's 29 / 29 -, the lock of a
  previous Clawline: control + 13).
- out_of_sprint (LEAD NOTE 3 (a); the airceil stage2b.txt 5 / 6.2): a down slash that starts out of the air dash /
  sprint (its Attack Cancel, or with the sprint's retained extra velocity) - a SIDE contact of it (her box bottom
  below the body's top) is not a pogo: the game hit her with the body first in 4 real cases the model scored as pogos
  (her model x in the sprint lags the recording by 0.1 - 0.5 u). Until a live probe settles it the body's contact is
  the outcome (search.simulate: a forced collision at the contact frame).

Switches (module level, the live worker and the bot set them from LiveCfg): ON (press_check), SIDE (side_spr); both off:
the search of M4d2.
"""
from __future__ import annotations

import math

import numpy as np
from numba import njit

from ssbot.knowledge import kinematics as km
from ssbot.knowledge.kin_jit import apply_events, f32, fixed_step, update
from ssbot.knowledge.kinematics import (
    ALPHA, ATK_PDIR, ATK_T, ATTACKING, BOUNCE, DS_REC, GROUND, MODE, MODE_T, P_ABIL, P_FDT, PHASE, QX, QY, RX0, RY0, SX,
    SY, TS, WF_S, XVX)

ON = [True]
SIDE = [True]
LOOK = 7                  # frames after a press its slash may still start (the 0.1 s attack queue: f + 1 .. f + 7)
FREE_MIN = 10             # frames after a pogo onset before the game starts a down slash (airceil: 0 / 657 earlier)
SIDE_DY = 0.0             # a contact with her box bottom below the body's top + SIDE_DY is a side contact
CLAW_LOCK_F = 13          # a Clawline from a previous one's control + 13 (env_jit.CLAW_NEXT_F; M0 9 / 9 at + 13)

# kin_trace columns: before the frame's Update (after its physics steps and events) ...
C_MODE, C_PH, C_GND, C_BNC, C_DSR, C_XVX, C_ATK0, C_ATKT0, C_MT = range(9)
# ... after it
C_ATK, C_ATKT, C_PDIR, C_UNL = range(9, 13)
NCOL = 13


@njit(cache=True, error_model="numpy")
def _trace(S0, masks, events, udt, P, TT, unl):
    """kin_jit.run_lane's frame loop for one lane at nominal timing (variant 0, the estimated phase - World.roll's),
    recording per frame t = 1 .. T the state before its Update and the attack after it; at frames with unl[t] also
    whether the same Update with the downspike lock lifted (BOUNCE / DS_REC cleared) starts a down slash."""
    T = masks.shape[0]
    out = np.zeros((T + 1, NCOL))
    x = S0.copy()
    fdt = P[P_FDT]
    out[0, C_MODE] = x[MODE]
    out[0, C_PH] = x[PHASE]
    out[0, C_GND] = x[GROUND]
    out[0, C_ATK] = x[ATTACKING]
    out[0, C_ATKT] = x[ATK_T]
    out[0, C_PDIR] = x[ATK_PDIR]
    for t in range(1, T + 1):
        m = masks[t - 1]
        ev = events[t - 1]
        if P[P_ABIL] != 0:
            x[RX0] = x[QX] + x[ALPHA] * (x[SX] - x[QX])
            x[RY0] = x[QY] + x[ALPHA] * (x[SY] - x[QY])
        dt = f32(udt * (x[TS] if x[WF_S] == 1.0 else x[TS] * x[WF_S]))
        a = x[ALPHA] + dt / fdt
        steps = np.int64(math.floor(a + 1e-9))
        x[ALPHA] = a - steps
        x[ALPHA] = min(max(x[ALPHA], 0.0), 1.0)
        for _ in range(steps):
            fixed_step(x, P, TT)
        apply_events(x, ev, P)
        out[t, C_MODE] = x[MODE]
        out[t, C_PH] = x[PHASE]
        out[t, C_GND] = x[GROUND]
        out[t, C_BNC] = x[BOUNCE]
        out[t, C_DSR] = x[DS_REC]
        out[t, C_XVX] = x[XVX]
        out[t, C_ATK0] = x[ATTACKING]
        out[t, C_ATKT0] = x[ATK_T]
        out[t, C_MT] = x[MODE_T]
        if unl[t] != 0:
            y = x.copy()
            y[BOUNCE] = -1.0
            y[DS_REC] = -1.0
            update(y, m, ev, dt, udt, P, TT)
            out[t, C_UNL] = 1.0 if (y[ATTACKING] > 0 and y[ATK_T] == 0.0 and y[ATK_PDIR] == 2.0) else 0.0
        update(x, m, ev, dt, udt, P, TT)
        out[t, C_ATK] = x[ATTACKING]
        out[t, C_ATKT] = x[ATK_T]
        out[t, C_PDIR] = x[ATK_PDIR]
    return out


def trace(W, S0: np.ndarray, masks: np.ndarray, events: np.ndarray | None = None, unl=()) -> np.ndarray:
    """kin_trace of a segment (search.World W: its params and terrain; masks as simulate rolls them, events per
    frame or None); unl: the rollout indices of the presses (the down-lock test there). [T + 1, NCOL]."""
    m = np.ascontiguousarray(np.asarray(masks, np.int64).reshape(-1))
    if not len(m):
        m = np.zeros(1, np.int64)
    ev = np.zeros(len(m), np.int64) if events is None else np.ascontiguousarray(
        np.asarray(events, np.int64).reshape(-1)[:len(m)])
    if len(ev) < len(m):
        ev = np.concatenate([ev, np.zeros(len(m) - len(ev), np.int64)])
    u = np.zeros(len(m) + 1, np.int64)
    for t in unl:
        if 1 <= int(t) <= len(m):
            u[int(t)] = 1
    udt = float(np.float32(W.params.frame_time))
    return _trace(np.ascontiguousarray(np.asarray(S0, np.float64).reshape(-1)), m, ev, udt, W.params.vector(),
                  W.TT, u)


def started(kt: np.ndarray, t: int) -> bool:
    """An attack starts in frame t's Update (it is on after it with its timer at 0, and was not already just
    started before it)."""
    return bool(kt[t, C_ATK] > 0 and kt[t, C_ATKT] == 0.0 and not (kt[t, C_ATK0] > 0 and kt[t, C_ATKT0] == 0.0))


def ds_start(kt: np.ndarray, t: int, look: int = LOOK, dt: float = 1.0 / 60.0) -> tuple:
    """(rollout index of the start, kind) of a down slash pressed at rollout index t: 'down' (a down slash starts at
    t .. t + look: the first attack that starts there), 'side' (that attack is not a down slash), 'lock' (none starts
    and kin's downspike lock alone held it at t, FREE_MIN frames or more after the pogo onset: credited at t), 'early'
    (the same inside the game's recovery: < FREE_MIN frames), 'none'."""
    n = len(kt) - 1
    for t2 in range(t, min(t + look, n) + 1):
        if started(kt, t2):
            return (t2, "down") if kt[t2, C_PDIR] == 2.0 else (t2, "side")
    if 1 <= t <= n and kt[t, C_UNL] > 0 and (kt[t, C_BNC] >= 0 or kt[t, C_DSR] >= 0):
        since = kt[t, C_DSR] / dt if kt[t, C_DSR] >= 0 else 99.0
        return (t, "lock") if since >= FREE_MIN - 0.5 else (t, "early")
    return t, "none"


def out_of_sprint(kt: np.ndarray, t: int) -> bool:
    """A slash started at rollout index t out of the air dash / sprint: its Attack Cancel (her mode before the
    Update the air sprint or the dash) or with the sprint's retained extra velocity on (HERO2 H2_SPR_ATK)."""
    return bool(int(kt[t, C_MODE]) in (km.M_SPRINT, km.M_DASH) or kt[t, C_XVX] != 0.0)


def claw_state_ok(kt: np.ndarray, t: int, P) -> bool:
    """env_jit.claw_allowed's state rule on her state before frame t's Update (the press P): airborne, normal control
    or the umbrella's float / deflate; HERO2 H2_CLAW_SPR: the air sprint too (the lock is the caller's)."""
    if kt[t, C_GND] > 0:
        return False
    m = int(kt[t, C_MODE])
    ph = kt[t, C_PH]
    if m == km.M_NORMAL:
        return True
    if m == km.M_SPRINT and ph <= 1.0 and (int(P[km.P_H2]) & km.H2_CLAW_SPR) != 0:
        return True
    return m == km.M_GLIDE and (ph == 2.0 or ph == 3.0)


def state_name(kt: np.ndarray, t: int) -> str:
    return f"{km.MODE_NAMES[int(kt[t, C_MODE])]}{int(kt[t, C_PH])}"


__all__ = ["ON", "SIDE", "LOOK", "FREE_MIN", "trace", "started", "ds_start", "out_of_sprint", "claw_state_ok",
           "state_name", "CLAW_LOCK_F"]
