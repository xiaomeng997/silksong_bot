"""Numba kernels of the map v2 hero envelope (ssbot.map2.envelope; docs/plans/forum_map_v2.md section 1 L2, stage M1).

A CLUSTER is one vertical trajectory with its reachable x as a set of intervals. Its vertical state is a kin_jit model
state (the same code the planner rolls, kinematics / kin_jit with SSBOT_FORUM_HERO2's calibration), carried in two
LANES: lane 0 holds left, lane 1 right in every frame, so their x are the cluster's extremes and their per-frame x
displacements (dlo, dhi) bound every member's: x intervals map [a, b] -> [a + dlo, b + dhi] (exact for the instant
run, an over-approximation inside the umbrella's inertia, a translation in the committed blocks: the dash, the air
sprint, the Clawline). The vertical does not depend on left / right (no walls in the tables), so both lanes keep the
same vertical state; the kernel counts any divergence (it is a bug).

Each frame every cluster rolls its physics steps once, then branches on the keys that change its vertical state or
mode (the jump key pressed / held / released, the dash pressed with a direction or held, the attack's cancels of the
umbrella and the sprint, the unhooked Clawline left / right) - a child per choice. Children whose canonical vertical
key (kin_jit's state without the horizontal fields, the timers that ran out canonicalised) is equal MERGE: their
interval sets unite (different event orders that end in the same state cost nothing). No snapping: keys are exact.
Danger boxes (her centre's configuration space) cut each child's intervals at its own height in each frame.

The unhooked Clawline is not in kin_jit: its block is the M0 track (ssbot.knowledge.hero2.claw_unhooked, ported per
frame), the lanes frozen meanwhile (their cooldowns tick), control at P + 32 (+ the throw variant) as an A1 start
(vy 0, the air dash and attack free) with the HarpoonDashEnd residual drift bounded per step by max(run, 12.46 x
0.923^k).

Time: frames (60 fps Update, where keys act and the FSM timers run) with the physics steps of each frame from the
lane's own phase, exactly as kin_jit.run_lane under nominal timing; the vertical curves are per 50 Hz step.

The count (forum.md 92): exact clusters do not stay at a few thousand - the air dash (its 14-frame air sprint, cancelled
at any frame, with or without jump held) and the Clawline (4 variants every frame) multiply them (A1, 16 frames:
23,831). The event limit (opts bits 8 .. 11: presses, releases of a hold that acts, the Clawline; going on is free)
gives the spec's segment family in milliseconds. A held key whose hold acts (hold_useful) is the default 'going on';
the dominance filter drops a child that only holds more useless keys than a sibling. The far layer's bands (band_n /
band_t: one discrete state, a y / vy hull) are a validated superset but stayed large with the dash and the Clawline.
"""
from __future__ import annotations

import math

import numpy as np
from numba import njit, prange
from numba import types
from numba.typed import Dict

from ssbot.knowledge.kin_jit import fixed_step, update, can_dash, f32, ge32
from ssbot.knowledge.kinematics import (
    K, PX, PY, QX, QY, SX, SY, VX, VY, ALPHA, GS, FACE, GROUND, MODE, MODE_T, JUMPING, JSTEPS, JDSTEPS, JQ, AQ,
    AIRHANG, ATTACKING, ATK_T, ATK_CD, RDIR, RSTEPS, DS_REC, BOUNCE, MOVE, JHELD, PREV, INV_T, LEDGE, TOUCH, PHASE,
    TS, QQ, LANDQ, WF_S, WSIDE, WTOUCH, CLING, CLING_CD, WSTICK, UNSTICK, WLOCK, WJ_V, WJ_CHAIN, WJQ, WSLASH, PREV_GS,
    GL_CD, DASH_T, DASH_CD, AIRDASHED, DQ, FALL_T, HARD, SP_X, WCON, SHOVE, RX0, RY0, JBUF, ATK_PDIR,
    B_JUMP, B_ATTACK, B_DASH, B_LEFT, B_RIGHT, M_NORMAL, M_GLIDE, M_DASH, M_SPRINT, M_HARD_LAND,
    P_FDT, P_RUN, P_HW, P_FOOT, P_HEAD, P_JSTEPS_MIN, P_GL_INFLATE, P_JQ, P_DQ, P_ATK_DUR, P_ATK_REC, P_ABIL,
    AB_DASH)

# ---- candidate codes (one per child): the vertical key bits of the frame's mask + a direction override --------
CB_J, CB_A, CB_D = B_JUMP, B_ATTACK, B_DASH          # 1, 2, 4
CB_DIR = 1 << 8         # both lanes press this direction this frame (a dash / Clawline press)
CB_RIGHT = 1 << 9
CB_CLAW = 1 << 10       # the unhooked Clawline pressed this frame (custom block)
CB_TF8 = 1 << 11        # its throw at P + 8 (the antic one frame shorter; 15 / 123 airborne in M0)
CB_CONT = 1 << 12       # inside the Clawline block: no update (the lanes are frozen)
CB_JH = 1 << 13         # an air dash pressed with jump already held (no new press): the dash's steps turn gravity off
                        # and the hang ramp keeps the scale low while jump is held (kin_jit; reachable when jump was
                        # pressed earlier without opening the umbrella: in an attack's recovery, the umbrella's 0.1 s
                        # cooldown, after a jump's hang) - offered at every air dash press, an over-approximation for
                        # the first frames of an airtime

# ---- options (forward / gen_cands): the Clawline and its P + 8 throw; for experiments, mechanics switched off
OPT_CLAW, OPT_TF8, OPT_NO_DASH, OPT_NO_JH, OPT_NO_CANCEL, OPT_NO_UMB = 1, 2, 4, 8, 16, 32
# the attack pressed in normal control (its lock blocks the umbrella / the dash and delays a jump press's effect:
# the slashes do not move her, so it only matters through those locks - off by default, see forum.md 92)
OPT_ATK = 64
# bits 8 .. 11: the event limit (0: none) - the 'segment family' of the spec: the choices other than going on

# ---- custom per-cluster fields ---------------------------------------------------------------------------------
C_CJ, C_CD, C_CTF, C_CLOCK, C_RV, C_RD, C_EV = range(7)
NC = 7                  # C_EV: the events (choices other than going on) since the start - not a key (a merge keeps the
                        # fewest: a member may then take one event more than the limit, its positions still real)
# the Clawline (ssbot.knowledge.hero2, M0: 173 unhooked presses)
CLAW_THROW_F, CLAW_DASH_F, CLAW_CATCH_F, CLAW_CTRL_F = 9, 19, 26, 32
CLAW_SPEED = 70.0
CLAW_ANTIC_DX, CLAW_ANTIC_DY = 0.975, 0.875
CLAW_CATCH_DECEL = 0.75
CLAW_END_DECAY = 0.923
CLAW_VY_LO, CLAW_VY_HI = -10.0, 5.0
CLAW_NEXT_F = 13

# ---- end-condition bits per cluster and frame ------------------------------------------------------------------
COND_ATK = 1          # an attack pressed next frame swings at once (normal control, attack ready; the umbrella's cancel)
COND_DSLASH = 2       # ... and airborne (the down slash)
COND_CLAW = 4         # the unhooked Clawline may be pressed (the hooked one: the same state, a target in the ray)
COND_GROUND = 8       # standing / walking (normal control on the ground)
COND_RUN = 16         # the ground sprint (17.5 u/s)
COND_FLOAT = 32       # the umbrella's Float Idle
COND_AIR = 64         # airborne
COND_CLAWBLK = 128    # inside a Clawline block (committed)
COND_DASHED = 256     # the air dash used

# ---- the canonical vertical key ---------------------------------------------------------------------------------
_KEEP = np.array([PY, QY, SY, VY, GS, GROUND, MODE, MODE_T, JUMPING, JSTEPS, JQ, AQ, AIRHANG, ATTACKING, DS_REC,
                  BOUNCE, JHELD, INV_T, LEDGE, TOUCH, PHASE, QQ, LANDQ, WSIDE, WTOUCH, CLING, WSTICK, UNSTICK, WLOCK,
                  WJ_V, WJ_CHAIN, WJQ, WSLASH, PREV_GS, DASH_T, AIRDASHED, DQ, FALL_T, HARD, WCON, SHOVE, ATK_PDIR,
                  RDIR, RSTEPS], dtype=np.int64)
NK0 = _KEEP.shape[0]
_JH = int(np.flatnonzero(_KEEP == JHELD)[0])
_MT = int(np.flatnonzero(_KEEP == MODE_T)[0])
_INV = int(np.flatnonzero(_KEEP == INV_T)[0])
_FT = int(np.flatnonzero(_KEEP == FALL_T)[0])
_ADS = int(np.flatnonzero(_KEEP == AIRDASHED)[0])
_ATK = int(np.flatnonzero(_KEEP == ATTACKING)[0])
_HARD = int(np.flatnonzero(_KEEP == HARD)[0])
assert _KEEP[0] == PY and _KEEP[1] == QY and _KEEP[2] == SY and _KEEP[3] == VY   # the band key's slots
_JQ = int(np.flatnonzero(_KEEP == JQ)[0])
_DQ = int(np.flatnonzero(_KEEP == DQ)[0])
_AQ = int(np.flatnonzero(_KEEP == AQ)[0])
_QQ = int(np.flatnonzero(_KEEP == QQ)[0])
# canonicalised: JDSTEPS (min with jump_steps_min: only '>=' is read), ATK_T (only while attacking), the cooldowns
# that stop at <= 0 (ATK_CD, CLING_CD, GL_CD, DASH_CD, JBUF: max 0), PREV (jump / attack / dash bits), the direction of
# a committed block (dash FACE, sprint SP_X, Clawline), the custom fields
K_JDS, K_ATKT, K_ATKCD, K_CLCD, K_GLCD, K_DCD, K_JBUF, K_PREV, K_DIR = range(NK0, NK0 + 9)
K_C0 = NK0 + 9
NKEY = K_C0 + NC
# fields a no-op press may change (the filter compares children of one parent without them): the press edges and
# the queues a fresh press reproduces (a buffered jump / queued dash fires in the frame a new press would)
_NOOP_SKIP = np.array([QQ, AQ], dtype=np.int64)
# (the jump / dash queues and the jump buffer are NOT skipped: a queued jump or dash fires by itself while its key is
# held - a forced behaviour, not an option a fresh press reproduces)


@njit(cache=True, error_model="numpy")
def jheld_matters(x):
    """Whether holding jump can still change the vertical: the hang (gravity scale < 1, or a hang still to come after
    a take-off), the dash (its steps turn gravity off; the hang ramp keeps it low while jump is held). A later dash
    with jump held is the dash candidate CB_JH, not a state."""
    if x[GS] < 1.0 or x[MODE] == M_DASH:
        return True
    return x[GROUND] <= 0 and x[AIRHANG] <= 0


@njit(cache=True, error_model="numpy")
def hold_useful(x, P):
    """The key bits whose holding can still act in this state (jump: the rise, the release's cut while rising, the
    hang, the umbrella, a queued jump, the buffer at a RegainControl; dash: the dash / sprint, a queued dash).
    Holding any other key only blocks its next press."""
    m = x[MODE]
    u = 0
    # (a release while rising halves vy - in normal control, the dash, the hard landing: Update reads the key there)
    cut = (m == M_NORMAL or m == M_DASH or m == M_HARD_LAND) and x[VY] > 0 and x[JDSTEPS] >= P[P_JSTEPS_MIN]
    if (x[JUMPING] > 0 or cut or jheld_matters(x) or m == M_GLIDE or (0 <= x[JQ] <= P[P_JQ])
            or (x[JBUF] > 0 and m != M_NORMAL)):
        u |= B_JUMP
    if m == M_DASH or m == M_SPRINT or (0 <= x[DQ] <= P[P_DQ]):
        u |= B_DASH
    return u


@njit(cache=True, error_model="numpy")
def vkey(x, cu, P, floor, out):
    for i in range(NK0):
        out[i] = x[_KEEP[i]]
    out[K_JDS] = min(x[JDSTEPS], P[P_JSTEPS_MIN])
    out[K_ATKT] = x[ATK_T] if x[ATTACKING] > 0 else 0.0
    out[K_ATKCD] = max(x[ATK_CD], 0.0)
    out[K_CLCD] = max(x[CLING_CD], 0.0)
    out[K_GLCD] = max(x[GL_CD], 0.0)
    out[K_DCD] = max(x[DASH_CD], 0.0)
    # the jump buffer acts only at a RegainControl (the umbrella's landing / Deflate end, the sprint's end): kept
    # outside normal control; the queues act only while they run (a queued jump <= jump_queue_steps, a queued dash
    # <= dash_queue_steps; a queued attack needs the attack held, never done here); past that they count on unread
    # (the buffered jump and the queued jump need a floor to act: none in free space)
    m = x[MODE]
    prv = np.int64(x[PREV])
    out[K_JBUF] = max(x[JBUF], 0.0) if (floor and m != M_NORMAL and m != M_HARD_LAND) else 0.0
    out[_JQ] = x[JQ] if (floor and (prv & B_JUMP) != 0 and 0 <= x[JQ] <= P[P_JQ]) else -1.0
    out[_DQ] = x[DQ] if ((prv & B_DASH) != 0 and 0 <= x[DQ] <= P[P_DQ]) else -1.0
    out[_AQ] = -1.0
    out[_QQ] = -1.0
    out[K_PREV] = np.float64(np.int64(x[PREV]) & (B_JUMP | B_ATTACK | B_DASH))
    # JHELD is rewritten by every Update in control; the steps read it only for the air hang
    # (and in the dash: its steps turn gravity off and the hang ramp brings it back at once unless jump is held -
    # so a jump held in the air while the dash is still available is a state of its own)
    if not jheld_matters(x):
        out[_JH] = 0.0
    d = 0.0
    if cu[C_CJ] >= 0:
        d = cu[C_CD]
    elif m == M_DASH:
        d = x[FACE]
    elif m == M_SPRINT:
        d = 1.0 if x[SP_X] > 0 else -1.0
    out[K_DIR] = d
    for i in range(NC):
        out[K_C0 + i] = cu[i]
    out[K_C0 + C_EV] = 0.0
    # the FSM timer where no transition reads it: normal control, Float Idle / Bump, the held air sprint
    ph = x[PHASE]
    if m == M_NORMAL or (m == M_GLIDE and (ph == 2.0 or ph == 5.0)) or (m == M_SPRINT and ph == 1.0):
        out[_MT] = 0.0
    for i in range(NKEY):
        out[i] += 0.0                 # -0.0 -> 0.0 (equal keys must hash equally)


@njit(cache=True, error_model="numpy")
def khash(k):
    h = np.uint64(1469598103934665603)
    v = k.view(np.uint64)
    for i in range(v.shape[0]):
        h = (h ^ v[i]) * np.uint64(1099511628211)
        h ^= h >> np.uint64(29)
    return np.int64(h & np.uint64(0x7FFFFFFFFFFFFFFF))


@njit(cache=True, error_model="numpy")
def keq(a, b):
    for i in range(a.shape[0]):
        if a[i] != b[i]:
            return False
    return True


_NOOP_POS = np.zeros(NK0, dtype=np.bool_)
for _q in range(NK0):
    for _s in _NOOP_SKIP:
        if _KEEP[_q] == _s:
            _NOOP_POS[_q] = True


@njit(cache=True, error_model="numpy")
def keq_noop(a, b, ub):
    """Child b adds nothing to child a of the same parent: equal keys except that b holds at least the keys a holds
    and none of b's extra held keys acts in b's state (ub: hold_useful) - so a can press whatever b can."""
    pa = np.int64(a[K_PREV])
    pb = np.int64(b[K_PREV])
    if (pa & ~pb) != 0:
        return False
    if ((pb & ~pa) & ub) != 0:
        return False
    for i in range(a.shape[0]):
        if i == K_PREV:
            continue
        if i < NK0 and _NOOP_POS[i]:
            continue
        if a[i] != b[i]:
            return False
    return True


# ---- one lane's frame (kin_jit.run_lane under nominal timing) ----------------------------------------------------

@njit(cache=True, error_model="numpy")
def lane_timing(x, udt, P):
    """The drawn position this frame's FixedUpdates start from, the frame's scaled dt and physics steps."""
    x[RX0] = x[QX] + x[ALPHA] * (x[SX] - x[QX])
    x[RY0] = x[QY] + x[ALPHA] * (x[SY] - x[QY])
    dt = f32(udt * (x[TS] if x[WF_S] == 1.0 else x[TS] * x[WF_S]))
    a = x[ALPHA] + dt / P[P_FDT]
    steps = np.int64(math.floor(a + 1e-9))
    x[ALPHA] = min(max(a - steps, 0.0), 1.0)
    return dt, steps


@njit(cache=True, error_model="numpy")
def tick_frozen(x, dt, udt):
    """A frozen lane's Update timers (the Clawline block: no kin_jit update, the cooldowns still run)."""
    if x[ATK_CD] > 0:
        x[ATK_CD] = f32(x[ATK_CD] - dt)
    if x[DASH_CD] > 0:
        x[DASH_CD] = f32(x[DASH_CD] - dt)
    if x[GL_CD] > 0:
        x[GL_CD] = f32(x[GL_CD] - dt)
    if x[CLING_CD] > 0:
        x[CLING_CD] = f32(x[CLING_CD] - dt)
    x[INV_T] = max(f32(x[INV_T] - dt), 0.0)
    if x[JBUF] > 0:
        x[JBUF] = f32(x[JBUF] - udt)


# ---- the unhooked Clawline -----------------------------------------------------------------------------------

@njit(cache=True, error_model="numpy")
def claw_allowed(x, cu):
    if cu[C_CJ] >= 0 or cu[C_CLOCK] > 0 or x[GROUND] > 0:
        return False
    m = x[MODE]
    if m == M_NORMAL:
        return True
    return m == M_GLIDE and (x[PHASE] == 2.0 or x[PHASE] == 3.0)


@njit(cache=True, error_model="numpy")
def claw_enter(x, cu, d, tf):
    """The press at P (this frame's Update): Harpoon Antic OnEnter - ClampVelocity2D (x +-20, y -10 .. 5), one
    DecelerateXY (0.975, 0.875)."""
    x[VX] = min(max(x[VX], -20.0), 20.0) * CLAW_ANTIC_DX
    x[VY] = min(max(x[VY], CLAW_VY_LO), CLAW_VY_HI) * CLAW_ANTIC_DY
    cu[C_CJ] = 0.0
    cu[C_CD] = d
    cu[C_CTF] = tf
    cu[C_RV] = 0.0
    cu[C_RD] = 0.0


@njit(cache=True, error_model="numpy")
def claw_frame(x, cu, steps, P):
    """One frame of the block for a lane (velocities in its VX / VY): the steps' decel and move, the frame end's
    OnEnter (throw: v 0; dash: 70 u/s along d; catch: x 0.75). Returns True at control."""
    j = np.int64(cu[C_CJ]) + 1
    sh = np.int64(cu[C_CTF]) - CLAW_THROW_F
    tF, dF, cF, n = CLAW_THROW_F + sh, CLAW_DASH_F + sh, CLAW_CATCH_F + sh, CLAW_CTRL_F + sh
    fdt = P[P_FDT]
    vx, vy = x[VX], x[VY]
    px, py = x[PX], x[PY]
    for _ in range(steps):
        if j <= tF:
            vx *= CLAW_ANTIC_DX
            vy *= CLAW_ANTIC_DY
        elif j > cF:
            vx *= CLAW_CATCH_DECEL
        x[QX] = px
        x[QY] = py
        px += vx * fdt
        py += vy * fdt
    if j == tF:
        vx = 0.0
        vy = 0.0
    elif j == dF:
        vx = cu[C_CD] * CLAW_SPEED
        vy = 0.0
    elif j == cF:
        vx *= CLAW_CATCH_DECEL
    x[PX] = px
    x[PY] = py
    x[SX] = px
    x[SY] = py
    x[VX] = vx
    x[VY] = vy
    return j >= n


@njit(cache=True, error_model="numpy")
def claw_control(x):
    """Control after the unhooked Clawline: an A1 start (vy 0, no bounce), the attack and the air dash free (M0:
    24 / 24, 17 / 17 presses at control + 2 ..; the dash reset is assumed, an over-approximation if it was used),
    every key released (the block took 32 frames: any held key may have been let go)."""
    x[MODE] = M_NORMAL
    x[MODE_T] = 0.0
    x[PHASE] = 0.0
    x[VX] = 0.0
    x[VY] = 0.0
    x[GS] = 1.0
    x[PREV_GS] = 1.0
    x[JUMPING] = 0.0
    x[JSTEPS] = 0.0
    x[BOUNCE] = -1.0
    x[ATTACKING] = 0.0
    x[AIRHANG] = 1.0
    x[GROUND] = 0.0
    x[AIRDASHED] = 0.0
    x[DASH_T] = 0.0
    x[DQ] = -1.0
    x[AQ] = -1.0
    x[JQ] = -1.0
    x[QQ] = -1.0
    x[JBUF] = 0.0
    x[FALL_T] = 0.0
    x[HARD] = 0.0
    x[MOVE] = 0.0
    x[JHELD] = 0.0
    x[PREV] = 0.0
    x[DS_REC] = -1.0
    x[RDIR] = 0.0
    x[LEDGE] = 0.0
    x[TOUCH] = 0.0
    x[LANDQ] = 0.0
    x[QX] = x[PX]
    x[QY] = x[PY]
    x[SX] = x[PX]
    x[SY] = x[PY]


# ---- candidates -------------------------------------------------------------------------------------------------

@njit(cache=True, error_model="numpy")
def gen_cands(x, cu, P, opts, dt, out):
    """The vertical choices of this frame for a cluster after its steps (x: its lane 1), fewest presses first.
    Returns the count. Only choices that can change the vertical state or the mode: a jump press (the jump, the
    umbrella, the sprint's jump cancel), a held jump where holding acts (the rise, the hang, the umbrella, a queued
    jump), a dash press left / right (normal control, the dash ready) or as the umbrella's cancel, a held dash where
    holding acts (the dash / sprint, a queued dash: then with its direction), the attack as the umbrella's or the
    sprint's cancel (in normal control the Wanderer's slashes do not move her: only restrictive, never offered),
    the unhooked Clawline left / right. The children are deduplicated afterwards (no-op presses)."""
    if cu[C_CJ] >= 0:
        out[0] = CB_CONT
        return 1
    m = x[MODE]
    maxev = (opts >> 8) & 15           # the event limit (0: none): reached -> only going on (below)
    ph = x[PHASE]
    prev = np.int64(x[PREV])
    ground = x[GROUND] > 0
    jo = np.zeros(2, dtype=np.int64)
    nj = 1
    if (prev & B_JUMP) != 0:
        if (hold_useful(x, P) & B_JUMP) != 0:                     # holding is the default (the umbrella, the rise), releasing the choice
            jo[0] = CB_J
            jo[1] = 0
            nj = 2
    elif m != M_HARD_LAND:
        jo[nj] = CB_J                  # (in the dash too: a held jump keeps the dash's gravity off ramping as a hang)
        nj += 1
    do = np.zeros(3, dtype=np.int64)
    nd = 1
    jh = False
    cdash = can_dash_upd(x, dt, P)
    if (prev & B_DASH) != 0:
        if x[DQ] >= 0 and cdash:
            do[1] = CB_D | CB_DIR
            do[2] = CB_D | CB_DIR | CB_RIGHT
            nd = 3
            jh = True                  # (on the ground too: the dash's steps turn gravity off)
        elif m == M_DASH or m == M_SPRINT or 0 <= x[DQ] <= P[P_DQ]:
            do[0] = CB_D               # holding is going on (the sprint, a queued dash), releasing the choice
            do[1] = 0
            nd = 2
    else:
        if m == M_NORMAL and cdash:
            do[1] = CB_D | CB_DIR
            do[2] = CB_D | CB_DIR | CB_RIGHT
            nd = 3
            jh = True                  # (on the ground too: the dash's steps turn gravity off)
        elif (m == M_GLIDE and ph >= 1) or m == M_DASH or m == M_SPRINT:
            do[1] = CB_D               # the umbrella's dash cancel; the air sprint's hold from its loop's first frame
            nd = 2
    ao = np.zeros(2, dtype=np.int64)
    na = 1
    if (prev & B_ATTACK) == 0 and ((m == M_GLIDE and ph >= 1) or m == M_SPRINT):
        ao[1] = CB_A
        na = 2
    elif ((opts & OPT_ATK) != 0 and (prev & B_ATTACK) == 0 and m == M_NORMAL and x[ATTACKING] <= 0
          and x[ATK_CD] <= 0):
        ao[1] = CB_A
        na = 2
    n = 0
    # fewest presses first: (j, d, a) in order of the sum of their indices
    for tot in range(0, 5):
        for a in range(na):
            for d in range(nd):
                for j in range(nj):
                    if j + (1 if d > 0 else 0) + a != tot:
                        continue
                    out[n] = jo[j] | do[d] | ao[a]
                    n += 1
    if jh:
        out[n] = CB_D | CB_DIR | CB_JH | CB_J
        out[n + 1] = CB_D | CB_DIR | CB_RIGHT | CB_JH | CB_J
        n += 2
    if m == M_NORMAL and not ground and (prev & B_JUMP) == 0:
        # jump held without a press (pressed earlier where the umbrella could not open: an attack's recovery, its
        # cooldown): it keeps / starts the air hang (a no-op elsewhere, dropped by the dominance filter)
        out[n] = CB_J | CB_JH
        n += 1
    if (opts & OPT_CLAW) != 0 and claw_allowed(x, cu):
        out[n] = CB_CLAW | CB_DIR
        out[n + 1] = CB_CLAW | CB_DIR | CB_RIGHT
        n += 2
        if (opts & OPT_TF8) != 0:
            out[n] = CB_CLAW | CB_TF8 | CB_DIR
            out[n + 1] = CB_CLAW | CB_TF8 | CB_DIR | CB_RIGHT
            n += 2
    if maxev > 0 and cu[C_EV] >= maxev:
        # the event limit reached: only the free choices (going on, a released useless hold, a queued dash firing)
        pb = prev & (B_JUMP | B_DASH | B_ATTACK)
        us = hold_useful(x, P)
        k = 0
        for i in range(n):
            if i == 0 or n_events(out[i], pb, us) == 0.0:
                out[k] = out[i]
                k += 1
        n = k
    if (opts & (OPT_NO_DASH | OPT_NO_JH | OPT_NO_CANCEL | OPT_NO_UMB)) != 0:   # experiments: mechanics off
        k = 0
        for i in range(n):
            c = out[i]
            if (opts & OPT_NO_DASH) != 0 and (c & CB_D) != 0:
                continue
            if (opts & OPT_NO_JH) != 0 and (c & CB_JH) != 0:
                continue
            if (opts & OPT_NO_CANCEL) != 0 and m == M_GLIDE and (c & (CB_A | CB_D)) != 0:
                continue
            if (opts & OPT_NO_UMB) != 0 and m == M_NORMAL and not ground and (c & CB_J) != 0 and                     (prev & B_JUMP) == 0:
                continue
            out[k] = c
            k += 1
        n = k
    return n


@njit(cache=True, error_model="numpy")
def can_dash_upd(x, dt, P):
    """can_dash as the dash input sees it in this frame's Update: after the attack timer's step (the slash's
    recovery / duration may end first)."""
    a = x[ATTACKING]
    t = x[ATK_T]
    if x[MODE] == M_NORMAL and a > 0:
        t = f32(t + dt)
        if ge32(t, P[P_ATK_DUR]):
            a = 0.0
    if (np.int64(P[P_ABIL]) & AB_DASH) == 0 or x[MODE] != M_NORMAL or x[DASH_CD] > 0:
        return False
    if a > 0 and t < P[P_ATK_REC]:
        return False
    return x[GROUND] > 0 or x[AIRDASHED] <= 0 or x[WSIDE] != 0


@njit(cache=True, error_model="numpy")
def n_events(cd, pbits, useful):
    """The events a candidate spends (the event limit): each key pressed, each held key released while its hold
    acts (useful), the Clawline press 1; going on, a released useless hold and the block's frames 0."""
    if (cd & CB_CONT) != 0:
        return 0.0
    if (cd & CB_CLAW) != 0:
        return 1.0
    cb = cd & (B_JUMP | B_DASH | B_ATTACK)
    if (cd & CB_JH) != 0:
        cb &= ~B_JUMP                  # the jump held without a press: its press was earlier (not counted here)
        pbits &= ~B_JUMP
    ch = cb ^ pbits
    e = 0
    for b in (B_JUMP, B_DASH, B_ATTACK):
        if (ch & b) != 0 and ((cb & b) != 0 or (useful & b) != 0):
            e += 1
    return np.float64(e)


@njit(cache=True, error_model="numpy")
def lane_mask(cand, lane):
    m = cand & (B_JUMP | B_ATTACK | B_DASH)
    if (cand & CB_DIR) != 0:
        return m | (B_RIGHT if (cand & CB_RIGHT) != 0 else B_LEFT)
    return m | (B_RIGHT if lane == 1 else B_LEFT)


@njit(cache=True, error_model="numpy")
def cond_of(x, cu, P):
    c = 0
    m = x[MODE]
    ph = x[PHASE]
    if cu[C_CJ] >= 0:
        return COND_CLAWBLK | COND_AIR
    atk = (m == M_NORMAL and x[ATTACKING] <= 0 and x[ATK_CD] <= 0) or \
        (m == M_GLIDE and (ph == 2.0 or ph == 3.0 or ph == 5.0 or (ph == 1.0 and x[MODE_T] >= 0.075)))
    air = x[GROUND] <= 0
    if atk:
        c |= COND_ATK
        if air:
            c |= COND_DSLASH
    if claw_allowed(x, cu):
        c |= COND_CLAW
    if not air and m == M_NORMAL:
        c |= COND_GROUND
    if m == M_SPRINT and ph == 2.0:
        c |= COND_RUN
    if m == M_GLIDE and ph == 2.0:
        c |= COND_FLOAT
    if air:
        c |= COND_AIR
    if x[AIRDASHED] > 0:
        c |= COND_DASHED
    return c


@njit(cache=True, error_model="numpy")
def residual(xl, cu, steps, P):
    """The HarpoonDashEnd drift after an unhooked Clawline's control, on the lane on its side: a member without a key
    moves the residual (x 0.923 per step), one with the key toward it the run speed, one turning cancels it - so the
    extreme moves max(run, residual) per step. The residual is dropped once below the run speed (a member then never
    passes the lane) or on the ground. Returns the extra x of the lane on its side (signed)."""
    rv = cu[C_RV]
    if rv <= 0:
        return 0.0
    if xl[GROUND] > 0 or xl[MODE] != M_NORMAL:
        cu[C_RV] = 0.0
        cu[C_RD] = 0.0
        return 0.0
    run = P[P_RUN]
    ex = 0.0
    for _ in range(steps):
        if rv > run:
            ex += (rv - run) * P[P_FDT]
        rv *= CLAW_END_DECAY
    if rv <= run:
        rv = 0.0
    out = ex * cu[C_RD]
    cu[C_RV] = rv
    if rv == 0.0:
        cu[C_RD] = 0.0
    return out


# ---- the far layer: bands ----------------------------------------------------------------------------------------
# A BAND is a cluster whose two lanes differ in the vertical as well: lane 0 holds the bottom corner (lowest y, lowest
# vy), lane 1 the top corner, both in the same discrete state (every key field but y / vy). Under one discrete state
# the vertical rules are monotone in (y, vy) (gravity, the caps, the float's AccelerateToY, the fixed Inflate / rise /
# dash speeds, the release's halving), so the corners bound every member: the band covers y in [lane 0, lane 1].
# Where a threshold splits it (the hang starts at vy < 0, the release halves only vy > 0, ...) the lanes' discrete
# states differ: the band splits into two, each with the whole y range (an over-approximation). Bands merge when their
# discrete keys and their y / vy bins agree (qy, qv): the coarse far layer (spec: 0.25 u, coarse vy) - never used for
# witnesses, only for the regions.

@njit(cache=True, error_model="numpy")
def band_key(k1, x0, x1, hh, qy, qv, P, out):
    """The band merge key from the top lane's exact key k1: y / vy slots replaced by the bins of both corners."""
    for i in range(k1.shape[0]):
        out[i] = k1[i]
    out[0] = math.floor((x0[PY] + hh) / qy)
    out[1] = math.floor((x1[PY] + hh) / qy)
    out[2] = math.floor(x0[VY] / qv)
    out[3] = math.floor(x1[VY] / qv)
    # the locks are not keys in the far layer: a merged band takes the least restrictive (merge_locks)
    out[K_ATKCD] = 0.0
    out[K_CLCD] = 0.0
    out[K_GLCD] = 0.0
    out[K_DCD] = 0.0
    out[K_ATKT] = 0.0
    out[_INV] = 0.0
    out[_FT] = 0.0
    out[K_C0 + C_CLOCK] = 0.0
    out[K_C0 + C_RV] = 0.0
    out[_ADS] = 0.0                    # the air dash available, attacking, the hard landing: least restrictive
    out[_ATK] = 0.0
    out[_HARD] = 0.0
    out[K_PREV] = np.float64(np.int64(out[K_PREV]) & hold_useful(x1, P))   # held keys that act stay keys
    for i in range(4):
        out[i] += 0.0


@njit(cache=True, error_model="numpy")
def merge_locks(a0, a1, ca, b0, b1, cb):
    """Band merge (a absorbs b): every lock the least restrictive of the two (cooldowns the shorter, the attack's
    recovery the further, the fall timer the shorter, the Clawline lock the shorter, the residual drift the larger),
    on both lanes alike."""
    for f in (ATK_CD, CLING_CD, GL_CD, DASH_CD, INV_T, FALL_T, AIRDASHED, ATTACKING, HARD):
        v = min(a1[f], b1[f])
        a0[f] = v
        a1[f] = v
    pv = np.float64(np.int64(a1[PREV]) & np.int64(b1[PREV]) | (np.int64(a1[PREV]) & (B_LEFT | B_RIGHT)))
    a1[PREV] = pv
    a0[PREV] = np.float64(np.int64(a0[PREV]) & np.int64(b0[PREV]) | (np.int64(a0[PREV]) & (B_LEFT | B_RIGHT)))
    v = max(a1[ATK_T], b1[ATK_T])
    a0[ATK_T] = v
    a1[ATK_T] = v
    ca[C_CLOCK] = min(ca[C_CLOCK], cb[C_CLOCK])
    ca[C_RV] = max(ca[C_RV], cb[C_RV])


@njit(cache=True, error_model="numpy")
def dkey_eq(a, b):
    """Equal discrete states (the exact keys without y / vy)."""
    for i in range(4, a.shape[0]):
        if a[i] != b[i]:
            return False
    return True


_YF = np.array([PY, QY, SY, VY, RY0], dtype=np.int64)
_XF = np.array([PX, QX, SX, VX, FACE, MOVE, RX0], dtype=np.int64)


@njit(cache=True, error_model="numpy")
def set_x(dst, src):
    """The horizontal fields (and the left / right bits of the previous mask, which the umbrella and the skid read)."""
    for i in range(_XF.shape[0]):
        dst[_XF[i]] = src[_XF[i]]
    lr = B_LEFT | B_RIGHT
    dst[PREV] = np.float64((np.int64(dst[PREV]) & ~lr) | (np.int64(src[PREV]) & lr))


@njit(cache=True, error_model="numpy")
def set_y(dst, src):
    for i in range(_YF.shape[0]):
        dst[_YF[i]] = src[_YF[i]]


@njit(cache=True, error_model="numpy")
def hull_y(lo, hi, src_lo, src_hi):
    """Merge a band's corners into (lo, hi): component-wise min / max of the vertical fields."""
    for i in range(_YF.shape[0]):
        f = _YF[i]
        if src_lo[f] < lo[f]:
            lo[f] = src_lo[f]
        if src_hi[f] > hi[f]:
            hi[f] = src_hi[f]


# ---- interval helpers --------------------------------------------------------------------------------------------

@njit(cache=True, error_model="numpy")
def cut_danger(lo, hi, ylo, yhi, boxes, b0, b1, olo, ohi, wlo, whi):
    """[lo, hi] minus the boxes (x0, y0, x1, y1) of rows b0 .. b1 - 1 whose y range holds [ylo, yhi] (closed; a band
    loses only the x every member's height is hit at); the pieces into olo / ohi (wlo / whi: work space of the same
    size). Returns their count."""
    n = 1
    olo[0] = lo
    ohi[0] = hi
    cap = olo.shape[0]
    for b in range(b0, b1):
        if not (boxes[b, 1] <= ylo and yhi <= boxes[b, 3]):
            continue
        cx0 = boxes[b, 0]
        cx1 = boxes[b, 2]
        m = 0
        for k in range(n):
            a = olo[k]
            c = ohi[k]
            if cx1 < a or cx0 > c:
                if m < cap:
                    wlo[m] = a
                    whi[m] = c
                    m += 1
                continue
            if cx0 > a and m < cap:
                wlo[m] = a
                whi[m] = cx0
                m += 1
            if cx1 < c and m < cap:
                wlo[m] = cx1
                whi[m] = c
                m += 1
        for k in range(m):
            olo[k] = wlo[k]
            ohi[k] = whi[k]
        n = m
        if n == 0:
            break
    return n


# ---- the forward pass ---------------------------------------------------------------------------------------------

@njit(cache=True, error_model="numpy")
def forward(L0, cu0, ivs0, T, udt, P, TT, boxes, box_off, opts, cap_frame, cap_pc, cap_iv, cap_cl,
            keep_keys, band_t, band_n, qy, qv):
    """The cluster forward pass from one start cluster.

    L0 [2, K]: the start's lanes (lane 0 left extreme, lane 1 right), cu0 [NC], ivs0 [m, 2] its x intervals; T frames;
    udt the unscaled frame time; P, TT kin_jit's parameter vector and packed terrain; boxes [nb, 4] the danger boxes in
    her centre's space, frame t's rows box_off[t] .. box_off[t + 1] - 1 (frame 0 = the start); caps: clusters per frame,
    pieces, intervals and clusters in all. Returns the per-frame cluster table, the intervals, the pieces (child, parent,
    candidate, the piece's interval, the parent's lane displacements) and the stats."""
    fdt = P[P_FDT]
    hh = 0.5 * (P[P_HEAD] - P[P_FOOT])
    floor = TT[0] > 0                               # any floor / ceiling segment in the terrain
    # outputs
    cl_off = np.zeros(T + 2, dtype=np.int64)
    cl_y = np.empty(cap_cl)
    cl_vy = np.empty(cap_cl)
    cl_cond = np.empty(cap_cl, dtype=np.int64)
    cl_mode = np.empty(cap_cl, dtype=np.int64)
    cl_phase = np.empty(cap_cl, dtype=np.int64)
    cl_iv0 = np.empty(cap_cl, dtype=np.int64)
    cl_ivn = np.empty(cap_cl, dtype=np.int64)
    IV = np.empty((cap_iv, 2))
    pc_cl = np.empty(cap_pc, dtype=np.int64)
    pc_par = np.empty(cap_pc, dtype=np.int64)
    pc_cand = np.empty(cap_pc, dtype=np.int64)
    pc_lo = np.empty(cap_pc)
    pc_hi = np.empty(cap_pc)
    pc_dlo = np.empty(cap_pc)
    pc_dhi = np.empty(cap_pc)
    cl_ylo = np.empty(cap_cl)
    stats = np.zeros((T + 1, 8), dtype=np.int64)   # clusters, pieces, dead (cut), diverged, merged, children tried,
    #                                                band mode (0 / 1), band splits
    cl_key = np.empty((cap_cl if keep_keys else 1, NKEY))
    flags = np.zeros(4, dtype=np.int64)            # overflow: frame, pieces, intervals, clusters
    # frame 0: the start cluster
    cur = np.empty((cap_frame, 2, K))
    cuc = np.empty((cap_frame, NC))
    nxt = np.empty((cap_frame, 2, K))
    cun = np.empty((cap_frame, NC))
    cur[0, 0, :] = L0[0]
    cur[0, 1, :] = L0[1]
    cuc[0, :] = cu0
    ncl = 1
    niv = 0
    npc = 0
    lo0 = ivs0[0, 0]
    hi0 = ivs0[0, 1]
    for i in range(ivs0.shape[0]):
        IV[niv, 0] = ivs0[i, 0]
        IV[niv, 1] = ivs0[i, 1]
        niv += 1
        lo0 = min(lo0, ivs0[i, 0])
        hi0 = max(hi0, ivs0[i, 1])
    cl_y[0] = L0[1, PY] + hh
    cl_ylo[0] = L0[0, PY] + hh
    cl_vy[0] = L0[1, VY]
    cl_cond[0] = cond_of(L0[1], cu0, P)
    cl_mode[0] = np.int64(L0[1, MODE])
    cl_phase[0] = np.int64(L0[1, PHASE])
    cl_iv0[0] = 0
    cl_ivn[0] = niv
    cl_off[0] = 0
    cl_off[1] = 1
    stats[0, 0] = 1
    ntot = 1
    # per-frame work buffers
    kbuf = np.empty((cap_frame, NKEY))
    khs = np.empty(cap_frame, dtype=np.int64)
    knext = np.empty(cap_frame, dtype=np.int64)
    ch_first = np.empty(cap_frame, dtype=np.int64)
    fp_next = np.empty(8 * cap_frame, dtype=np.int64)
    fp_cap = fp_next.shape[0]
    fp_ch = np.empty(fp_cap, dtype=np.int64)
    fp_par = np.empty(fp_cap, dtype=np.int64)
    fp_cand = np.empty(fp_cap, dtype=np.int64)
    fp_lo = np.empty(fp_cap)
    fp_hi = np.empty(fp_cap)
    fp_dlo = np.empty(fp_cap)
    fp_dhi = np.empty(fp_cap)
    tmp = np.empty((2, K))
    tcu = np.empty(NC)
    cands = np.empty(32, dtype=np.int64)
    kid = np.empty((48, 2, K))
    kcu = np.empty((48, NC))
    kkey = np.empty((48, NKEY))
    kkeep = np.empty(48, dtype=np.bool_)
    kcand = np.empty(48, dtype=np.int64)
    kuse = np.empty(48, dtype=np.int64)
    key2 = np.empty(NKEY)
    key1 = np.empty(NKEY)
    band = False
    wlo = np.empty(64)
    whi = np.empty(64)
    klo = np.empty(64)
    khi = np.empty(64)
    olo = np.empty(64)
    ohi = np.empty(64)
    sl = np.empty(256)
    sh_ = np.empty(256)
    for t in range(1, T + 1):
        if not band and ((band_t >= 0 and t >= band_t) or (band_n > 0 and ncl > band_n)):
            band = True                              # from here on the far layer (stays on)
        stats[t, 6] = 1 if band else 0
        d = Dict.empty(key_type=types.int64, value_type=types.int64)
        nch = 0
        nfp = 0
        b0 = box_off[t]
        b1 = box_off[t + 1]
        base_g = cl_off[t - 1]
        for c in range(ncl):
            g = base_g + c                          # the parent's global index
            # this frame's physics (or the Clawline block)
            tmp[0, :] = cur[c, 0]
            tmp[1, :] = cur[c, 1]
            for i in range(NC):
                tcu[i] = cuc[c, i]
            x0l = tmp[0, PX]
            x0h = tmp[1, PX]
            ctl = False
            inblk = tcu[C_CJ] >= 0
            dtl = 0.0
            for ln in range(2):
                dt, steps = lane_timing(tmp[ln], udt, P)
                dtl = dt
                if inblk:
                    ctl = claw_frame(tmp[ln], tcu, steps, P)
                    tick_frozen(tmp[ln], dt, udt)
                else:
                    for _ in range(steps):
                        fixed_step(tmp[ln], P, TT)
            if inblk:
                tcu[C_CJ] = tcu[C_CJ] + 1.0
                if ctl:
                    rv = abs(tmp[1, VX])               # the catch's x speed at control (12.46 nominal)
                    claw_control(tmp[0])
                    claw_control(tmp[1])
                    tcu[C_CJ] = -1.0
                    tcu[C_CLOCK] = CLAW_NEXT_F
                    tcu[C_RD] = tcu[C_CD]
                    tcu[C_RV] = rv
            else:
                if tcu[C_CLOCK] > 0:
                    tcu[C_CLOCK] -= 1.0
                ex = residual(tmp[1] if tcu[C_RD] > 0 else tmp[0], tcu, steps, P)
                if ex > 0:
                    tmp[1, PX] += ex
                    tmp[1, SX] = tmp[1, PX]
                elif ex < 0:
                    tmp[0, PX] += ex
                    tmp[0, SX] = tmp[0, PX]
            # candidates
            nc = gen_cands(tmp[1], tcu, P, opts, dtl, cands)
            pbits = np.int64(tmp[1, PREV]) & (B_JUMP | B_DASH | B_ATTACK)
            u0 = hold_useful(tmp[1], P)
            stats[t, 5] += nc
            nk = 0
            for k in range(nc):
                cd = cands[k]
                kid[nk, 0, :] = tmp[0]
                kid[nk, 1, :] = tmp[1]
                for i in range(NC):
                    kcu[nk, i] = tcu[i]
                if (cd & CB_CONT) != 0:
                    pass
                elif (cd & CB_CLAW) != 0:
                    dd = 1.0 if (cd & CB_RIGHT) != 0 else -1.0
                    tf = 8.0 if (cd & CB_TF8) != 0 else 9.0
                    claw_enter(kid[nk, 0], kcu[nk], dd, tf)
                    claw_enter(kid[nk, 1], kcu[nk], dd, tf)
                    tick_frozen(kid[nk, 0], dtl, udt)
                    tick_frozen(kid[nk, 1], dtl, udt)
                else:
                    for ln in range(2):
                        if (cd & CB_JH) != 0:
                            kid[nk, ln, PREV] = np.float64(np.int64(kid[nk, ln, PREV]) | B_JUMP)
                        update(kid[nk, ln], lane_mask(cd, ln), 0, dtl, udt, P, TT)
                vkey(kid[nk, 1], kcu[nk], P, floor, key1)
                vkey(kid[nk, 0], kcu[nk], P, floor, key2)
                kcand[nk] = cd
                kkeep[nk] = True
                kcu[nk, C_EV] += n_events(cd, pbits, u0)
                kuse[nk] = hold_useful(kid[nk, 1], P)
                if not band:
                    # an exact cluster: the lanes must agree (vertical independent of left / right)
                    if not keq(key1, key2):
                        stats[t, 3] += 1
                    kkey[nk, :] = key1
                    nk += 1
                elif dkey_eq(key1, key2):
                    band_key(key1, kid[nk, 0], kid[nk, 1], hh, qy, qv, P, kkey[nk])
                    nk += 1
                else:
                    # a threshold inside the band: split into the bottom lane's state and the top lane's, each over
                    # the whole y range
                    stats[t, 7] += 1
                    kid[nk + 1, 0, :] = kid[nk, 1]
                    kid[nk + 1, 1, :] = kid[nk, 1]
                    for i in range(NC):
                        kcu[nk + 1, i] = kcu[nk, i]
                    kcand[nk + 1] = cd
                    kkeep[nk + 1] = True
                    kuse[nk + 1] = hold_useful(kid[nk + 1, 1], P)
                    kuse[nk] = hold_useful(kid[nk, 0], P)
                    # (nk + 1): the top lane's state; its lane 0 gets the bottom corner's x and y
                    set_x(kid[nk + 1, 0], kid[nk, 0])
                    set_y(kid[nk + 1, 0], kid[nk, 0])
                    # (nk): the bottom lane's state; its lane 1 gets the top corner's x and y
                    kid[nk, 1, :] = kid[nk, 0]
                    set_x(kid[nk, 1], kid[nk + 1, 1])
                    set_y(kid[nk, 1], kid[nk + 1, 1])
                    for j in range(2):
                        vkey(kid[nk + j, 1], kcu[nk + j], P, floor, key1)
                        band_key(key1, kid[nk + j, 0], kid[nk + j, 1], hh, qy, qv, P, kkey[nk + j])
                    nk += 2
                # dominance among the parent's children (same x set): a child that holds more keys and is otherwise
                # equal adds nothing (either order)
                for j in range(nk - 1, nk):
                    for q in range(j):
                        if not kkeep[q]:
                            continue
                        if keq_noop(kkey[q], kkey[j], kuse[j]):
                            kkeep[j] = False
                            break
                        if keq_noop(kkey[j], kkey[q], kuse[q]):
                            kkeep[q] = False
                            if kcu[q, C_EV] < kcu[j, C_EV]:
                                kcu[j, C_EV] = kcu[q, C_EV]
            # the parent's intervals, shifted per child, cut by the danger at the child's height (range)
            for k in range(nk):
                if not kkeep[k]:
                    continue
                dlo = kid[k, 0, PX] - x0l
                dhi = kid[k, 1, PX] - x0h
                ya = kid[k, 0, PY] + hh
                yb = kid[k, 1, PY] + hh
                ylo = min(ya, yb)
                yhi = max(ya, yb)
                npcs = 0
                for q in range(cl_ivn[g]):
                    a = IV[cl_iv0[g] + q, 0] + dlo
                    b = IV[cl_iv0[g] + q, 1] + dhi
                    if b0 < b1:
                        m = cut_danger(a, b, ylo, yhi, boxes, b0, b1, olo, ohi, wlo, whi)
                        for r in range(m):
                            if npcs < 64:
                                klo[npcs] = olo[r]
                                khi[npcs] = ohi[r]
                                npcs += 1
                    else:
                        if npcs < 64:
                            klo[npcs] = a
                            khi[npcs] = b
                            npcs += 1
                if npcs == 0:
                    stats[t, 2] += 1
                    continue
                # find / insert the child
                h = khash(kkey[k])
                idx = -1
                if h in d:
                    j = d[h]
                    while j >= 0:
                        if keq(kbuf[j], kkey[k]):
                            idx = j
                            break
                        j = knext[j]
                if idx < 0:
                    if nch >= cap_frame:
                        flags[0] = 1
                        continue
                    idx = nch
                    nch += 1
                    nxt[idx, 0, :] = kid[k, 0]
                    nxt[idx, 1, :] = kid[k, 1]
                    for i in range(NC):
                        cun[idx, i] = kcu[k, i]
                    kbuf[idx, :] = kkey[k]
                    khs[idx] = h
                    knext[idx] = d[h] if h in d else -1
                    d[h] = idx
                    ch_first[idx] = -1
                else:
                    stats[t, 4] += 1
                    # the merged lanes: the extreme velocities (the inertia modes; equal elsewhere) and, for bands,
                    # the vertical corners
                    if kid[k, 0, VX] < nxt[idx, 0, VX]:
                        nxt[idx, 0, VX] = kid[k, 0, VX]
                    if kid[k, 1, VX] > nxt[idx, 1, VX]:
                        nxt[idx, 1, VX] = kid[k, 1, VX]
                    if kcu[k, C_EV] < cun[idx, C_EV]:
                        cun[idx, C_EV] = kcu[k, C_EV]
                    if band:
                        hull_y(nxt[idx, 0], nxt[idx, 1], kid[k, 0], kid[k, 1])
                        merge_locks(nxt[idx, 0], nxt[idx, 1], cun[idx], kid[k, 0], kid[k, 1], kcu[k])
                for r in range(npcs):
                    if nfp >= fp_cap:
                        flags[1] = 1
                        break
                    fp_ch[nfp] = idx
                    fp_par[nfp] = g
                    fp_cand[nfp] = kcand[k]
                    fp_lo[nfp] = klo[r]
                    fp_hi[nfp] = khi[r]
                    fp_dlo[nfp] = dlo
                    fp_dhi[nfp] = dhi
                    fp_next[nfp] = ch_first[idx]
                    ch_first[idx] = nfp
                    nfp += 1
        # finalize the frame: union each child's pieces, write the cluster rows and the pieces
        gb = ntot
        if ntot + nch > cap_cl:
            flags[3] = 1
            nch = cap_cl - ntot
        for c in range(nch):
            gc = gb + c
            m = 0
            j = ch_first[c]
            while j >= 0 and m < 256:
                sl[m] = fp_lo[j]
                sh_[m] = fp_hi[j]
                m += 1
                j = fp_next[j]
            # insertion sort by lo
            for i in range(1, m):
                a = sl[i]
                b = sh_[i]
                q = i - 1
                while q >= 0 and sl[q] > a:
                    sl[q + 1] = sl[q]
                    sh_[q + 1] = sh_[q]
                    q -= 1
                sl[q + 1] = a
                sh_[q + 1] = b
            cl_iv0[gc] = niv
            n0 = niv
            for i in range(m):
                if niv > n0 and sl[i] <= IV[niv - 1, 1] + 1e-9:
                    if sh_[i] > IV[niv - 1, 1]:
                        IV[niv - 1, 1] = sh_[i]
                else:
                    if niv >= cap_iv:
                        flags[2] = 1
                        break
                    IV[niv, 0] = sl[i]
                    IV[niv, 1] = sh_[i]
                    niv += 1
            cl_ivn[gc] = niv - n0
            if niv > n0:
                for ln in range(2):
                    dx = (IV[n0, 0] if ln == 0 else IV[niv - 1, 1]) - nxt[c, ln, PX]
                    nxt[c, ln, PX] += dx
                    nxt[c, ln, QX] += dx
                    nxt[c, ln, SX] += dx
            cl_y[gc] = nxt[c, 1, PY] + hh
            cl_ylo[gc] = nxt[c, 0, PY] + hh
            cl_vy[gc] = nxt[c, 1, VY]
            cl_cond[gc] = cond_of(nxt[c, 1], cun[c], P)
            cl_mode[gc] = np.int64(nxt[c, 1, MODE])
            cl_phase[gc] = np.int64(nxt[c, 1, PHASE])
            if keep_keys:
                cl_key[gc, :] = kbuf[c]
        for j in range(nfp):
            if fp_ch[j] >= nch:
                continue
            if npc >= cap_pc:
                flags[1] = 1
                break
            pc_cl[npc] = gb + fp_ch[j]
            pc_par[npc] = fp_par[j]
            pc_cand[npc] = fp_cand[j]
            pc_lo[npc] = fp_lo[j]
            pc_hi[npc] = fp_hi[j]
            pc_dlo[npc] = fp_dlo[j]
            pc_dhi[npc] = fp_dhi[j]
            npc += 1
        ntot += nch
        cl_off[t + 1] = ntot
        stats[t, 0] = nch
        stats[t, 1] = nfp
        # swap buffers
        cur, nxt = nxt, cur
        cuc, cun = cun, cuc
        ncl = nch
        if ncl == 0:
            for tt in range(t + 1, T + 1):
                cl_off[tt + 1] = ntot
            break
    return (cl_off, cl_y[:ntot], cl_ylo[:ntot], cl_vy[:ntot], cl_cond[:ntot], cl_mode[:ntot], cl_phase[:ntot], cl_iv0[:ntot],
            cl_ivn[:ntot], IV[:niv], pc_cl[:npc], pc_par[:npc], pc_cand[:npc], pc_lo[:npc], pc_hi[:npc],
            pc_dlo[:npc], pc_dhi[:npc], cl_key[:ntot] if keep_keys else cl_key[:0], stats, flags)


# ---- table rasters ---------------------------------------------------------------------------------------------

@njit(cache=True, error_model="numpy")
def union_rows(b, xa, xb):
    """(bin, xa, xb) entries -> per bin the union of the intervals, sorted by (bin, xa): [n, 3]."""
    n = b.shape[0]
    # sort by (bin, xa): bins are small ints, combined lexicographically into one key
    comp = np.empty(n)
    lo = xa.min() if n else 0.0
    hi = xa.max() if n else 0.0
    span = hi - lo + 1.0
    for i in range(n):
        comp[i] = b[i] * span + (xa[i] - lo)
    idx = np.argsort(comp)
    out = np.empty((n, 3))
    m = 0
    for k in range(n):
        i = idx[k]
        if m > 0 and out[m - 1, 0] == b[i] and xa[i] <= out[m - 1, 2] + 1e-9:
            if xb[i] > out[m - 1, 2]:
                out[m - 1, 2] = xb[i]
        else:
            out[m, 0] = b[i]
            out[m, 1] = xa[i]
            out[m, 2] = xb[i]
            m += 1
    return out[:m]


# ---- the reference rollout (kin_jit + the Clawline block + the residual) ---------------------------------------

B_CLAW = 1 << 30      # the reference rollout's Clawline key bit (not an oracle button)


@njit(cache=True, error_model="numpy")
def ref_rollout(S0, cu0, masks, udt, P, TT, out_xy, out_mode):
    """One key sequence from S0: kin_jit's frame loop, a B_CLAW press where claw_allowed starts the unhooked
    Clawline's block (towards her facing; the throw variant from bit 31: 8 if set), and after control the residual
    drift (no key: the residual; the key toward it: the run; turning: cancelled). out_xy [T + 1, 2] her box centre,
    out_mode [T + 1]: the mode (-1 in the Clawline block)."""
    x = S0.copy()
    cu = cu0.copy()
    hh = 0.5 * (P[P_HEAD] - P[P_FOOT])
    T = masks.shape[0]
    out_xy[0, 0] = x[PX]
    out_xy[0, 1] = x[PY] + hh
    out_mode[0] = np.int64(x[MODE])
    fdt = P[P_FDT]
    run = P[P_RUN]
    for t in range(1, T + 1):
        m = masks[t - 1]
        dt, steps = lane_timing(x, udt, P)
        if cu[C_CJ] >= 0:
            ctl = claw_frame(x, cu, steps, P)
            tick_frozen(x, dt, udt)
            cu[C_CJ] += 1.0
            if ctl:
                rv = abs(x[VX])
                claw_control(x)
                cu[C_CJ] = -1.0
                cu[C_CLOCK] = CLAW_NEXT_F
                cu[C_RD] = cu[C_CD]
                cu[C_RV] = rv
                update(x, m & ~B_CLAW & ~(1 << 31), 0, dt, udt, P, TT)
        else:
            if cu[C_CLOCK] > 0:
                cu[C_CLOCK] -= 1.0
            for _ in range(steps):
                px0 = x[PX]
                fixed_step(x, P, TT)
                if cu[C_RV] > 0:
                    if x[GROUND] > 0 or x[MODE] != M_NORMAL:
                        cu[C_RV] = 0.0
                    else:
                        mv = x[MOVE]
                        if mv == 0:
                            x[PX] += cu[C_RV] * cu[C_RD] * fdt
                            x[SX] = x[PX]
                        elif mv == -cu[C_RD]:
                            cu[C_RV] = 0.0
                        cu[C_RV] *= CLAW_END_DECAY
            if (m & B_CLAW) != 0 and claw_allowed(x, cu):
                d = x[FACE]
                if (m & B_RIGHT) != 0 and (m & B_LEFT) == 0:
                    d = 1.0
                elif (m & B_LEFT) != 0 and (m & B_RIGHT) == 0:
                    d = -1.0
                x[FACE] = d
                claw_enter(x, cu, d, 8.0 if (m & (1 << 31)) != 0 else 9.0)
                tick_frozen(x, dt, udt)
                x[PREV] = np.float64(m & ~B_CLAW & ~(1 << 31))
            else:
                update(x, m & ~B_CLAW & ~(1 << 31), 0, dt, udt, P, TT)
        out_xy[t, 0] = x[PX]
        out_xy[t, 1] = x[PY] + hh
        out_mode[t] = -1 if cu[C_CJ] >= 0 else np.int64(x[MODE])
    return x, cu


@njit(cache=True, parallel=True, error_model="numpy")
def ref_many(S0s, cu0s, masks, udt, P, TT):
    n, T = masks.shape
    xy = np.empty((n, T + 1, 2))
    md = np.empty((n, T + 1), dtype=np.int64)
    for i in prange(n):
        ref_rollout(S0s[i], cu0s[i], masks[i], udt, P, TT, xy[i], md[i])
    return xy, md


# ---- the witness tracker -------------------------------------------------------------------------------------

@njit(cache=True, error_model="numpy")
def _vbits(vm):
    m = vm & (B_JUMP | B_ATTACK | B_DASH)
    if (vm & CB_CLAW) != 0:
        m |= B_CLAW | ((1 << 31) if (vm & CB_TF8) != 0 else 0)
    return m


@njit(cache=True, error_model="numpy")
def track(S0, cu0, vmask, tlo, thi, udt, P, TT, look, out_mask, out_xy):
    """Concrete keys for a witness: per frame t the vertical bits vmask[t - 1] (from the cluster chain: jump / dash /
    attack, a forced direction, the Clawline) and the horizontal key chosen greedily: each of left / none / right is
    rolled ahead (then held: `look` frames, through the whole Clawline block when a press is near - its drift is set
    by the key before the press), and the one whose positions stay closest to the tube [tlo, thi] (the x from which
    the target is still reachable, per frame) wins, the tube's centre breaking ties. out_mask [T] the full masks
    (B_CLAW for a Clawline press), out_xy [T + 1, 2] the re-simulated centre."""
    T = vmask.shape[0]
    x = S0.copy()
    cu = cu0.copy()
    hh = 0.5 * (P[P_HEAD] - P[P_FOOT])
    out_xy[0, 0] = x[PX]
    out_xy[0, 1] = x[PY] + hh
    LMAX = look + CLAW_CTRL_F + 4
    ms = np.zeros(LMAX + 1, dtype=np.int64)
    oxy = np.empty((LMAX + 2, 2))
    omd = np.empty(LMAX + 2, dtype=np.int64)
    one = np.zeros(1, dtype=np.int64)
    one_xy = np.empty((2, 2))
    one_md = np.empty(2, dtype=np.int64)
    for t in range(1, T + 1):
        vm = vmask[t - 1]
        if (vm & CB_DIR) != 0:
            best = B_RIGHT if (vm & CB_RIGHT) != 0 else B_LEFT
        elif (vm & CB_CONT) != 0:
            best = 0
        else:
            best = 0
            bd = 1e18
            nfr = min(look, T - t) + 1
            for f in range(1, 3):
                if t - 1 + f < T and (vmask[t - 1 + f] & CB_CLAW) != 0:
                    nfr = min(T - t + 1, f + CLAW_CTRL_F + 2)
            for hk in range(3):
                h = 0 if hk == 0 else (B_LEFT if hk == 1 else B_RIGHT)
                for f in range(nfr):
                    vf = vmask[t - 1 + f]
                    hf = h
                    if (vf & CB_DIR) != 0:
                        hf = B_RIGHT if (vf & CB_RIGHT) != 0 else B_LEFT
                    ms[f] = _vbits(vf) | hf
                xs = x.copy()
                if (vm & CB_JH) != 0:
                    xs[PREV] = np.float64(np.int64(xs[PREV]) | B_JUMP)
                ref_rollout(xs, cu, ms[:nfr], udt, P, TT, oxy[:nfr + 1], omd[:nfr + 1])
                dd = 0.0
                for f in range(1, nfr + 1):
                    k = t - 1 + f
                    v = oxy[f, 0]
                    out = max(tlo[k] - v, v - thi[k], 0.0)
                    dd += out * (4.0 if f == 1 else 1.0) + 1e-3 * abs(v - 0.5 * (tlo[k] + thi[k]))
                if dd < bd - 1e-12:
                    bd = dd
                    best = h
        m = _vbits(vm) | best
        out_mask[t - 1] = m
        one[0] = m
        if (vm & CB_JH) != 0:
            x[PREV] = np.float64(np.int64(x[PREV]) | B_JUMP)   # the jump held from an earlier (hidden) press
        x, cu = ref_rollout(x, cu, one, udt, P, TT, one_xy, one_md)
        out_xy[t, 0] = one_xy[1, 0]
        out_xy[t, 1] = one_xy[1, 1]
    return out_mask


@njit(cache=True, error_model="numpy")
def track_beam(S0, cu0, vmask, tlo, thi, udt, P, TT, B, out_mask, out_xy):
    """The witness keys by a beam search over left / none / right per frame (the vertical bits fixed by vmask): B
    horizontal states kept per frame, distinct in (x, vx, the held key, the facing, the Clawline residual), ranked by
    their distance to the tube [tlo, thi] (0 inside)
    with the tube's centre breaking ties; the last frame ranks by the distance to the target (tlo[T] = thi[T]). The
    beam keeps positions across the tube, so a block whose drift is set by the key before it (the Clawline's antic
    from the last step's x speed) finds the start it needs. Returns the best final distance."""
    T = vmask.shape[0]
    K_ = S0.shape[0]
    NCC = cu0.shape[0]
    hh = 0.5 * (P[P_HEAD] - P[P_FOOT])
    bx = np.empty((B, K_))
    bc = np.empty((B, NCC))
    bm = np.zeros((B, T), dtype=np.int64)
    bxy = np.zeros((B, T + 1, 2))
    nb = 1
    bx[0, :] = S0
    bc[0, :] = cu0
    bxy[0, 0, 0] = S0[PX]
    bxy[0, 0, 1] = S0[PY] + hh
    cx = np.empty((3 * B, K_))
    cc = np.empty((3 * B, NCC))
    cm = np.zeros((3 * B, T), dtype=np.int64)
    cxy = np.zeros((3 * B, T + 1, 2))
    cost = np.empty(3 * B)
    one = np.zeros(1, dtype=np.int64)
    one_xy = np.empty((2, 2))
    one_md = np.empty(2, dtype=np.int64)
    for t in range(1, T + 1):
        vm = vmask[t - 1]
        nc = 0
        for b in range(nb):
            for hk in range(3):
                if (vm & CB_DIR) != 0:
                    if hk > 0:
                        break
                    h = B_RIGHT if (vm & CB_RIGHT) != 0 else B_LEFT
                elif (vm & CB_CONT) != 0:
                    if hk > 0:
                        break
                    h = 0
                else:
                    h = 0 if hk == 0 else (B_LEFT if hk == 1 else B_RIGHT)
                m = _vbits(vm) | h
                xs = bx[b].copy()
                if (vm & CB_JH) != 0:
                    xs[PREV] = np.float64(np.int64(xs[PREV]) | B_JUMP)
                one[0] = m
                xn, cn = ref_rollout(xs, bc[b], one, udt, P, TT, one_xy, one_md)
                cx[nc, :] = xn
                cc[nc, :] = cn
                for s in range(t - 1):
                    cm[nc, s] = bm[b, s]
                cm[nc, t - 1] = m
                for s in range(t):
                    cxy[nc, s, 0] = bxy[b, s, 0]
                    cxy[nc, s, 1] = bxy[b, s, 1]
                cxy[nc, t, 0] = one_xy[1, 0]
                cxy[nc, t, 1] = one_xy[1, 1]
                v = one_xy[1, 0]
                out = max(tlo[t] - v, v - thi[t], 0.0)
                cost[nc] = out + 1e-3 * abs(v - 0.5 * (tlo[t] + thi[t]))
                nc += 1
        # keep the states outside the tube by their distance to it, and the ones inside spread across it (sorted by
        # x, evenly picked: the start a later block needs may sit at the tube's edge)
        inside = np.zeros(nc, dtype=np.bool_)
        for i in range(nc):
            inside[i] = cost[i] < 1e-3 * (thi[t] - tlo[t] + 1.0) + 1e-12 and                 tlo[t] - 1e-9 <= cx[i, PX] <= thi[t] + 1e-9
        ins = np.flatnonzero(inside)
        outs = np.flatnonzero(~inside)
        ins = ins[np.argsort(cx[ins, PX])]
        outs = outs[np.argsort(cost[outs])]
        pick = np.empty(nc, dtype=np.int64)
        npk = 0
        if t == T:
            o2 = np.argsort(cost[:nc])
            for q in range(nc):
                pick[npk] = o2[q]
                npk += 1
        else:
            ni = ins.shape[0]
            if ni > 0:
                # evenly spaced through the sorted inside states, then the rest
                used = np.zeros(ni, dtype=np.bool_)
                nsel = min(ni, B)
                for q in range(nsel):
                    k = (q * (ni - 1)) // max(nsel - 1, 1)
                    if not used[k]:
                        used[k] = True
                        pick[npk] = ins[k]
                        npk += 1
                for k in range(ni):
                    if not used[k]:
                        pick[npk] = ins[k]
                        npk += 1
            for q in range(outs.shape[0]):
                pick[npk] = outs[q]
                npk += 1
        nb = 0
        for q in range(npk):
            i = pick[q]
            dup = False
            for b in range(nb):
                if abs(bx[b, PX] - cx[i, PX]) < 1e-6 and abs(bx[b, VX] - cx[i, VX]) < 1e-6 and                         bx[b, MOVE] == cx[i, MOVE] and bx[b, FACE] == cx[i, FACE] and                         abs(bc[b, C_RV] - cc[i, C_RV]) < 1e-9:
                    dup = True
                    break
            if dup:
                continue
            bx[nb, :] = cx[i]
            bc[nb, :] = cc[i]
            for s in range(t):
                bm[nb, s] = cm[i, s]
            for s in range(t + 1):
                bxy[nb, s, 0] = cxy[i, s, 0]
                bxy[nb, s, 1] = cxy[i, s, 1]
            nb += 1
            if nb >= B:
                break
    for s in range(T):
        out_mask[s] = bm[0, s]
    for s in range(T + 1):
        out_xy[s, 0] = bxy[0, s, 0]
        out_xy[s, 1] = bxy[0, s, 1]
    return abs(bxy[0, T, 0] - tlo[T])
