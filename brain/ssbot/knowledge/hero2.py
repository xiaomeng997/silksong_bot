"""Map v2 stage M0: the hero's carved-out blocks and timings measured with the m0_probe (docs/plans/forum_map_v2.md
section 1 L2 / section 2 M0; forum.md 91; Forum_W_w7, Wanderer, 1.0.30000). The kinematics model itself (kin_jit) gets
the umbrella / pogo corrections behind SSBOT_FORUM_HERO2 (kinematics.hero2); this module holds what the model does not
simulate - the Clawline - and the measured numbers the M1 envelope tables and the M3 search take as carve-outs.

Frames are rendered 60 fps frames, steps 50 Hz physics steps (5 per 6 frames); P is the frame whose latched ACTION
mask first holds the key (STATE act.mask; the bot's decision STATE is two frames earlier). u are world units: x her box
centre, bb her box bottom above the Forum floor (3.015). Spreads are p10 / p50 / p90 over the trials named.

    from ssbot.knowledge import hero2
    tr = hero2.claw_unhooked(x0=20.0, bb0=3.1, vx0=0.0, vy0=-2.0, d=1, fs=[1, 1, 0, 1, ...])   # per frame from P
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

FDT = 0.02

# ---- the Clawline (Harpoon Dash FSM) ------------------------------------------------------------------------------
# unhooked (no enemy / wall in the 9.25 u ray; 173 live presses: 125 in the air, 48 on the ground):
#   Harpoon Antic from P (167 / 173), Take Control: gravity off; Antic OnEnter: ClampVelocity2D (x +-20, y -10 .. 5),
#   then DecelerateXY (x 0.975, y 0.875) per step;
#   Harpoon Throw at P + 9 (108 / 123 airborne; 8 / 10 with the antic clip's frame phase): v = 0 for 10 frames (the
#   needle flies 9.25 u ahead, 0.5 u down);
#   Dash at P + 19 (throw + 10): 70 u/s along the facing for Wait 0.1 s = 6 steps (8.4 u, 172 / 173) or 5 (7.0 u), y
#   held (ClampVelocity y +-5, gravity locked);
#   Catch at P + 26 (dash + 7 frames): DecelerateV2 0.75 per step (52.5, 39.4, 29.5, 22.2, 16.6, 12.46 u/s: 3.8 u or
#   2.4 u), the height held;
#   control at P + 32 (catch + 6; 30 .. 33): vx 12.46 u/s toward, vy 0 (no bounce: an A1 start, at rest vertically);
#   HarpoonDashEnd adds a decaying air-move velocity (the catch's vx, Decay 4: x 0.923 per step) that is skipped while a
#   direction key is held and cancelled by a turn: with no key she drifts on 1.62 u (0.81 / 2.17) to her landing.
#   The pull P -> control: 10.6 u (9.4 / 10.6 / 10.8, n 173); from the ground the hold is the Kick Up's 0.25 u.
CLAW_THROW_F = 9           # P + this: Harpoon Throw (v = 0)
CLAW_DASH_F = 19           # P + this: the dash (70 u/s)
CLAW_DASH_STEPS = 6        # its steps (5 in 1 / 173)
CLAW_CATCH_F = 26          # P + this: Harpoon Catch (x 0.75 per step)
CLAW_CTRL_F = 32           # P + this: control (30 .. 33)
CLAW_SPEED = 70.0
CLAW_ANTIC_DECEL = (0.975, 0.875)
CLAW_CATCH_DECEL = 0.75
CLAW_END_DECAY = 0.923     # the air-move velocity after control, per step (exp(-4 * 0.02))
CLAW_VY_CLAMP = (-10.0, 5.0)
# after an unhooked Clawline's control: the attack and the dash at once (24 / 24, 17 / 17 presses at control + 2 ..
# 24); the umbrella at once when high enough (CanFloat); the next Clawline only from control + 13 (0 / 9 presses at
# + 2 .. 12, 23 / 23 at + 13 .. 24): the FSM's Wait 0.2 s (can.harpoon turns true at + 10, the 0.16 s cooldown, but a
# press before the FSM is Idle again is lost). No longer cooldown: no 'Clawline ready' key for the tables.
CLAW_NEXT_F = 13
# hooked (an enemy in the ray; 49 presses from the ground at the Clapper 3.1 - 8.6 u away): the needle hits at P + 8 / 9
# (the enemy's TOOK DAMAGE that frame: an Idle Clapper's Dmg Attack and its next move start there, 38 / 40), the dash
# from P + 17 .. 19, its body's damage at P + 18 .. 24, control at P + 23 .. 32 (p50 26) with vy -10 for one frame and
# the forced bounce (vy 17.4); no i-frames; the attack at control + 10 / 11 (0.15 s); a second Clawline from control
# + 12 / 13 (0 / 18 at + 2 .. 11, 1 / 2 at + 12, 9 / 9 at + 13 .. 18), which cuts the bounce (vy clamped to 5, then
# x 0.875).
HOOK_NEEDLE_F = (8, 9)
HOOK_NEXT_F = 12


@dataclass
class ClawTrack:
    x: np.ndarray        # her box centre per frame from P (index 0 = P)
    bb: np.ndarray       # her box bottom above the floor
    vx: np.ndarray
    vy: np.ndarray
    ctrl: int            # the index of control


def hold_bb(bb_p: float, vy_p: float, steps: int = 7) -> float:
    """Her box bottom held from the throw to control, from her free-flight state at P (the model's rollout at the
    latched frame): the antic's clamp, then x 0.875 per step for `steps` steps (7 or 8 between P and the throw)."""
    v = min(max(vy_p, CLAW_VY_CLAMP[0]), CLAW_VY_CLAMP[1]) * CLAW_ANTIC_DECEL[1]
    return bb_p + FDT * v * sum(CLAW_ANTIC_DECEL[1] ** k for k in range(1, steps + 1))


def claw_unhooked(x0: float, bb0: float, vx0: float, vy0: float, d: int, fs, throw_f: int = CLAW_THROW_F
                  ) -> ClawTrack:
    """The unhooked Clawline from P to control: x0 / bb0 / vx0 / vy0 her free-flight state at the end of frame P's
    physics (the model's rollout at P), d the direction (+-1), fs the physics steps of the frames P + 1 .. (at least
    to control; 0 / 1 per frame), throw_f the antic's length (9 in the air in 51 / 60, 8 in 9; from the ground 7 / 8;
    the rest of the timeline follows it rigidly). Velocities change per step as the FSM states do."""
    fs = list(fs)
    sh = throw_f - CLAW_THROW_F
    T_F, D_F, C_F = CLAW_THROW_F + sh, CLAW_DASH_F + sh, CLAW_CATCH_F + sh
    n = CLAW_CTRL_F + sh
    if len(fs) < n:
        raise ValueError(f"fs needs {n} frames")
    # a state entered in frame j's Update sets the velocity in its OnEnter and runs its per-step actions from frame
    # j + 1's physics steps (DecelerateXY / V2 before each step's move): the antic from P (OnEnter: the clamp and one
    # decel), the throw from P + 9 (v = 0), the dash from P + 19 (70 u/s), the catch from P + 26 (OnEnter x 0.75)
    vx = min(max(vx0, -20.0), 20.0) * CLAW_ANTIC_DECEL[0]
    vy = min(max(vy0, CLAW_VY_CLAMP[0]), CLAW_VY_CLAMP[1]) * CLAW_ANTIC_DECEL[1]
    X, B, VX, VY = [x0], [bb0], [vx], [vy]
    x, bb = x0, bb0
    for j in range(1, n + 1):
        for _ in range(int(fs[j - 1])):
            if j <= T_F:                               # the antic's steps
                vx *= CLAW_ANTIC_DECEL[0]
                vy *= CLAW_ANTIC_DECEL[1]
            elif j > C_F:                              # the catch's steps
                vx *= CLAW_CATCH_DECEL
            x += vx * FDT
            bb += vy * FDT
        if j == T_F:                                   # OnEnters at the end of the frame
            vx = vy = 0.0
        elif j == D_F:
            vx, vy = d * CLAW_SPEED, 0.0
        elif j == C_F:
            vx *= CLAW_CATCH_DECEL
        X.append(x), B.append(bb), VX.append(vx), VY.append(vy)
    return ClawTrack(np.array(X), np.array(B), np.array(VX), np.array(VY), n)


# ---- the umbrella (Umbrella Float FSM) ---------------------------------------------------------------------------
# 165 float trials (fl_atk 110 + fl_claw 85 + drift 41 - the antic / inflate presses): Antic 5 - 6 frames
# (UmbrellaMotionX accel 8.5: vx +-8.5 at once with a key; decel 0.25 per step without), Inflate 12 frames (vx reset to
# 0 at its entry, then accel 1.0 / decel 0.25 per step with the previous frame's key, vy 0.5), Float Idle (the same x
# rule up to 8.5, vy -> -6 at 0.13 per step); 987 / 987, 2007 / 2138, 3822 / 3856 steps match UmbrellaMotionX with the
# key lag of one frame (the misses: frames with two steps and the Inflate's OnEnter step). The Deflate: 6 frames after
# the float (132 / 132), 7 when the release falls on the Inflate's last frame (26 / 27), gravity on, vx frozen (639 / 639
# steps dvx 0, whatever key), control after it (the instant run). A release with no key in the float drifts on ~3 u
# (8.5 u/s at 0.25 per step).
# The re-open after a close (44): a jump press before the FSM is Idle again (release + 11 .. 14 = the Deflate's 6 + its
# Cooldown 0.1 s) does nothing (0 / 18, holding does not help: a new press), from release + 12 the umbrella opens at once
# (13 / 13) when she is still >= 1.1 u up (CanFloat).
DEFLATE_F = 6
REOPEN_F = 12
# attack (down / side) pressed in the umbrella, frames to the slash (fl_atk, 110):
#   Float Idle, jump held: at once (22 / 22, no Deflate); on the jump's release frame: LOST (0 / 20; Float Idle's
#   ListenForJump END fires first, the Deflate runs, control 6 frames later, no slash); in the Deflate (release + 1 ..
#   6): at once (19 / 19, the Deflate's Attack Cancel); after it: at once (34 / 34); in the Inflate: lost at its frames
#   1 - 4 (6 / 6: ListenForAttack's 0.075 s delay), at once from its 6th (9 / 9; the 5th not sampled); in the umbrella's
#   antic (5 - 6 frames): lost (0 / 26). SP13a's "2 f" and
#   the air show's "~8 f": a press on (or latched before) the release frame - lost, the Deflate's 6 frames + the bot's 2.
ATK_INFLATE_DELAY_F = 5
# Clawline pressed in the umbrella (fl_claw, 85 + 9): Float Idle held or released the same frame: at once (43 / 43;
# HeroController.LookForQueueInput, isInCancelableFSMMove); Deflate / after: at once (16 / 16); the Umbrella Antic:
# lost (0 / 24); the Inflate: only when the key is still held at the Float Idle's start (the harpoon queue: 6 / 11,
# delays 1 - 9; the 5 lost were released before it).

# ---- the down slash, the pogo and the dash -----------------------------------------------------------------------
# 115 contacts on the Clapper (pogo + side, 181 tries): the contact P + 3 (66) / + 4 (40); the bounce: vy -10 on the
# contact frame, then the default bounce until the slash's "Bounce" event at P + 7 (an extra -10 frame, then one step
# of 17.4: kin_jit with HERO2), rise over the contact frame's box 3.74 u (p10 3.43, p90 4.09), apex contact + 21 / 22;
# a contact after the event (P + 8 ..): one bounce of one step, rise ~2.7 - 3.05; i-frames contact + 0 .. 8 / 9 (the 8
# DOWNSPIKE_INVULNERABILITY_STEPS). A SIDE contact (her box bottom below its body top, her box clear of it in x by
# 0.03 - 1.7 u, n 42): a full bounce in 41 (the miss: she had landed), the same i-frames.
# The hooked Clawline's forced bounce is the plain default bounce: 4.09 u over the control frame's box (19 / 19), apex
# control + 22 / 23 - the A2 start differs after a pogo (3.74) and after a Clawline (4.09).
POGO_RISE = (3.43, 3.74, 4.09)
CLAW_BOUNCE_RISE = 4.09
POGO_APEX_F = (21, 22)
POGO_IFRAMES_F = (0, 9)
# the slash cadence: the next swing 18 frames after the press at the earliest (the 0.3 s cooldown; a press at + 17 held
# two frames swings at + 18 from the queue, 4 / 5), after a whiff and after a pogo hit alike (n 41 / 57)
SLASH_NEXT_F = 18
# the air dash after a pogo: restored (ResetAirMoves; 28 / 28 pre-dashed contacts had can.dash false before and true
# at contact + 9 .. 14 = the 0.425 s dash cooldown since that dash); without an earlier dash it is free at contact + 3 / 4
# (the slash's recovery)
# the ground dash: 7 - 9 frames, 3.5 - 4.05 u; the next one from 25 frames after the press (the 0.425 s cooldown, any
# number of them); held: the Sprint 28 -> 17.5 u/s at 1.1 per step, steady 17.5 (843 frames), released after the Sprint
# Grace: the skid (x 0.85 per step, ~16 frames), with the key held the run after it
DASH_NEXT_F = 25
SPRINT_SPEED = 17.5
