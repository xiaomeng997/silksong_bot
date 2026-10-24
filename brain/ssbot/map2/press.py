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

M4 S1b (the two verifiers' findings on S1; HANDOFF 'Task map2 - stage M4' / 'S1b', forum.md 101; LiveCfg free_pogo,
ds_shrink, side_rule / side_lag, spr_xvx - their S1 values give S1's search):
- the lock credit by the bounce's cause (finding presses 1): after a down slash POGO the game's downSpikeRecovery runs
  9 - 11 frames (1,292 airborne pogo bounces in 60 show / film episodes: 9 253, 10 462, 11 466, <= 8 44, 15 - 23
  67), after a hooked Clawline's forced bounce 1 frame (54 / 54; slashes pressed 10 - 12 frames after it all started,
  0 - 1 frame late; s1bec_after_bounce.json): a press only kin's lock holds is credited FREE_POGO (12) frames after a pogo onset, FREE_MIN (10) after the
  hook's (ds_start's hook_onset: the frame of the hook's forced bounce - simulate's own, the realizer's node after a
  Clawline - is the lock's onset; a start state's running lock counts as a pogo's).
- the contact's slack (finding presses 2): both alternations must meet the robust body box SHRUNK by SHRINK (0.05 u)
  on every side - a contact on a sliver (1e-5 u^2 in a committed plan) is not a pogo (her model x is good to 0.01 -
  0.1 u); the danger checks keep the full (grown) boxes.
- the side rule (findings presses 3, others 1 / 2): out_of_sprint's extra-velocity clause only while |XVX| >= XVX_MIN
  (1 u/s; the residue 0.01 - 0.1 u/s of an earlier cancel is not 'out of the sprint'); the body's top is the HIGHEST
  of the records drawn at that frame (strike.union_tops; robust_boxes intersects them); SIDE_RULE 'lag' (default):
  the body meets her first when her hurtbox, carried SIDE_LAG (0.5 u: her model x in the sprint lags the recording by
  0.1 - 0.5 u, airceil stage2b 5) further in her travel direction, overlaps the body box at a frame from the slash's
  start to its contact - 'top' (S1's rule with the highest top): her box bottom below the body's top at the contact;
  'top0': S1's rule as it was (the robust box's top).
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
FREE_MIN = 10             # frames after a hooked Clawline's forced bounce before kin's lock is lifted (M0: the attack
#                           cooled to control + 10 / 11; the game's recovery 1 f there - S1b: 54 / 54)
FREE_POGO = [12]          # M4 S1b: the same after a down slash POGO (the game's recovery 9 - 11 f in 95 %; S1: 10)
SHRINK = [0.05]           # M4 S1b: a down slash contact must meet the body box shrunk by this (u) on every side (S1: 0)
SIDE_RULE = ["lag"]       # M4 S1b: the side rule out of the air sprint - 'lag' / 'top' / 'top0' (S1), module docstring
SIDE_LAG = [0.5]          # M4 S1b: her lead in the travel direction the 'lag' rule allows for (u)
XVX_MIN = [1.0]           # M4 S1b: the sprint's retained extra velocity counts from this |XVX| (u/s; S1: any non-zero)
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


def ds_start(kt: np.ndarray, t: int, look: int = LOOK, dt: float = 1.0 / 60.0, free_min: int | None = None,
             hook_onset: int | None = None) -> tuple:
    """(rollout index of the start, kind) of a down slash pressed at rollout index t: 'down' (a down slash starts at
    t .. t + look: the first attack that starts there), 'side' (that attack is not a down slash), 'lock' (none starts
    and kin's downspike lock alone held it at t, free_min frames or more after the bounce's onset: credited at t),
    'early' (the same inside the game's recovery: < free_min frames), 'none'. S1b: free_min (unless given) is
    FREE_MIN when the lock's onset (t - its age) is a hooked Clawline's forced bounce - hook_onset, its rollout index
    (<= 0: before the trace), within a frame - else FREE_POGO[0] (a pogo's, or a start state's running lock)."""
    n = len(kt) - 1
    for t2 in range(t, min(t + look, n) + 1):
        if started(kt, t2):
            return (t2, "down") if kt[t2, C_PDIR] == 2.0 else (t2, "side")
    if 1 <= t <= n and kt[t, C_UNL] > 0 and (kt[t, C_BNC] >= 0 or kt[t, C_DSR] >= 0):
        since = kt[t, C_DSR] / dt if kt[t, C_DSR] >= 0 else 99.0
        fm = free_min
        if fm is None:
            hook = hook_onset is not None and kt[t, C_DSR] >= 0 and abs((t - since) - hook_onset) <= 1.5
            fm = FREE_MIN if hook else FREE_POGO[0]
        return (t, "lock") if since >= fm - 0.5 else (t, "early")
    return t, "none"


def out_of_sprint(kt: np.ndarray, t: int) -> bool:
    """A slash started at rollout index t out of the air dash / sprint: its Attack Cancel (her mode before the
    Update the air sprint or the dash) or with the sprint's retained extra velocity on (HERO2 H2_SPR_ATK) - S1b: from
    |XVX| >= XVX_MIN[0] (XVX_MIN 0: any non-zero, S1)."""
    if int(kt[t, C_MODE]) in (km.M_SPRINT, km.M_DASH):
        return True
    xv = abs(float(kt[t, C_XVX]))
    return bool(xv != 0.0 and xv >= XVX_MIN[0])


def side_hit(pos: np.ndarray, rel: np.ndarray, tops, ts: int, c: int, face: int, hb: np.ndarray) -> int:
    """M4 S1b: the side rule for a down slash out of the air dash / sprint started at rollout index ts with its
    contact at c (pos: her transforms, hb: her kin boxes per rollout index; rel: the robust body boxes from the
    segment's start; tops: the highest top of the records per frame (strike.union_tops, from the segment's start) or
    None; face: her travel direction): the rollout index where the body meets her first, -1: a pogo. SIDE_RULE:
    'top0' / 'top' - her box bottom below the robust / the highest top at c (S1's rule: at c); 'lag' - her hurtbox
    carried SIDE_LAG[0] further in her travel direction overlaps the body (its x range, the highest top, its bottom)
    at a frame ts .. c (the first such frame)."""
    from ssbot.map2 import clapper as cm
    rule = SIDE_RULE[0]

    def top_at(k):
        if tops is not None and k < len(tops) and np.isfinite(tops[k]):
            return float(tops[k])
        return float(rel[k, 3])
    if rule in ("top0", "top"):
        tp = float(rel[c, 3]) if rule == "top0" else top_at(c)
        return c if hb[c, 1] < tp + SIDE_DY else -1
    lag = SIDE_LAG[0]
    d = 1 if face >= 0 else -1
    for k in range(max(ts, 0), c + 1):
        if k >= len(rel) or np.isnan(rel[k, 0]):
            continue
        x0, y0, x1, y1 = cm.hurtbox(float(pos[k, 0]), float(pos[k, 1]))
        if d > 0:
            x1 += lag
        else:
            x0 -= lag
        if y0 < top_at(k) and y1 > rel[k, 1] and x0 < rel[k, 2] and x1 > rel[k, 0]:
            return k
    return -1


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


def unmodelled(kt: np.ndarray, masks: np.ndarray, prev: int = 0) -> list:
    """T4 (the verifiers' finding: an attack pressed in the ground dash or the ground sprint - the Wanderer's dash
    attack, a lunge M4a measured 2.6 - 3.9 u off the model; kin_jit's stand-in regains control at once): the rollout
    indices t where masks press the attack with her state before frame t's Update on the ground in the dash or the
    sprint. The envelope never offers it and its reference drops it (env_jit.ref_rollout); a plan with one is not
    played (search.simulate)."""
    m = np.asarray(masks, np.int64).reshape(-1)
    out = []
    pm = int(prev)
    for i in range(len(m)):
        t = i + 1
        pressed = (int(m[i]) & km.B_ATTACK) != 0 and (pm & km.B_ATTACK) == 0
        pm = int(m[i])
        if not pressed or t >= len(kt) or kt[t, C_GND] <= 0:
            continue
        md = int(kt[t, C_MODE])
        if md == km.M_DASH or (md == km.M_SPRINT and kt[t, C_PH] >= 2.0):
            out.append(t)
    return out


def state_name(kt: np.ndarray, t: int) -> str:
    return f"{km.MODE_NAMES[int(kt[t, C_MODE])]}{int(kt[t, C_PH])}"


__all__ = ["ON", "SIDE", "LOOK", "FREE_MIN", "FREE_POGO", "SHRINK", "SIDE_RULE", "SIDE_LAG", "XVX_MIN", "trace",
           "started", "ds_start", "out_of_sprint", "side_hit", "claw_state_ok", "state_name", "CLAW_LOCK_F", "unmodelled"]
