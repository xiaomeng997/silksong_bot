"""The small runes with a low hop and slashes all through (task 1v1 SP8d; the person 2026-10-16: "for the small runes, if
the jump is timed precisely, you do not even need to jump higher than the Clapper and can slash the whole time";
forum.md 75).

SSBOT_FORUM_RUNE_LOWHOP (read by train.forum_planner_policy; since the SP8d A/B on with SSBOT_FORUM_V2, =0 off; one live
Clapper only): when
the Clapper (Song Heavy Sentry) enters Spell Antic the bot plays the cast as a script: on the ground in front of it,
side slashes on the 19-frame rhythm, and one jump per bomb that covers her, its press frame and hold length chosen so
her box bottom stays above that bomb's circle while it is lit and as low as that allows; slashes in the air on the
rhythm where the slash still meets its body. The planner takes over when she lands from the hop (or when the cast is
over and no bomb threatens her).

The facts (C:/ssbot/data/m2_play/sp8d, 1,005 live casts of the SP8a-c runs, game frames of 1/60 s, k from the Spell
Antic entry; C = the Cast 2 entry):
  timeline  Spell Antic 43-44 frames, Cast 1 6, Cast 2 at k 48-50 lasting 24-26, then Idle 16-17 (p50; to 40);
            the next move: Evade Scuttle 61 %, Slam Antic 18 %, Walk 8 %, Spell Antic 5 %.
  its body  Spell Antic 0-3: top 3.19 u above the floor, front 2.05 u from its centre; 4-7: 4.36 / 2.06; 8 on and
            Cast 1 and Cast 2 0-13: 4.78 / 1.84; Cast 2 14 on: 3.19 / 2.05; Idle 3.92 / 2.25.
  bombs     ring r's pair at x0 +- 4.2 r (x0 its x at C), centre y = its y - 3.8 (the top 2.83 u above the floor),
            circle r 2.166; ring r appears at C + 9.6 r (0 / 9-10 / 19-20 / 28-30), lights 20-21 frames after it
            appears (p5-p95), lit 6 frames (p95 7). So between x0 + 2.67 and x0 + 5.73 (her box's half width 0.25
            in) only ring 1 reaches her: one hop, timed to its appearance (C + 9-10).
  the hop   the kinematics model's ground jump per hold H (hero_wanderer_forum.json; its logged apex table agrees):
            the box bottom per frame j from the latched press (HOP_LO / HOP_HI: the lowest / highest of the timing
            lanes); H 12 peaks 3.55-3.67 u (below its head, 3.92), above 2.95 from j 11 to 22.
  the slash the side slash's lower edge is the Wanderer slash polygon's (attacks/wanderer.json) measured from her box
            centre: a press meets the body when that edge at the gap to its near edge is below its top (1,143 live
            presses: margin >= -0.1 hit 13 / 13, below -0.5 1 of 174).
  the default under v2 floats or jumps 4.8 u up (p50) at ring 1's light and misses its Idle body (126 presses in
            reach from 3.9-5.3 u up, 0 hits); 15 of 1,005 casts lost HP to a bomb (she was 0.4-2.3 u up).

The script (every mask for frame f + 2; k counts game frames from the antic entry on the game clock):
  stance  on the ground: walk into stand_lo .. stand_hi from its centre (centre to centre) and, from Cast 2 on, into
          x0_lo .. x0_hi from x0 (only ring 1 reaches there); stop dead inside. A side slash (attack 2 frames, the
          key toward it on the press frame) whenever our presses are slash_cd apart, the STATE's attack cooldown is
          over and the slash from her x meets its body box (x reach and the lower edge, spare).
  hop     planned on every tick once a bomb that covers her is seen (it appears unlit 20-21 frames before it
          lights): the lowest hold H in h_min .. h_max whose press frames P put her box bottom (the lowest lane) at
          least `margin` above that bomb's circle at her x over its whole lit window (+ pre / post frames) for at
          least `min_slack` choices of P; of those P the one with the most slashes that can still land by the landing
          (the highest lane; no slash on the Idle Clapper while the hold or a bomb window is on: a hit on the Idle
          Clapper starts its next move at once), then the middle. The jump held from P for H game frames, no second
          jump press (in the air it opens the umbrella); in the air the key toward it only to keep the slash's
          reach, never past x0_lo .. x0_hi while a bomb covers her.
  critical while the hold or a covering bomb's window is on, the script keeps the keys ahead of the slam playbook,
          the jump antic scripts and the evade chase (the policy does not call them then: they start a few frames
          later, from the air).
Abort (the planner decides again): HP lost, the Clapper gone or a second one alive, a jump cast's rune circle over her
stance, a start in the air that does not land before the hop. SP11-0 (SSBOT_FORUM_TWO_GUARD; step(guard=...)): with two
Clappers no start / abort ("guard", outside the critical window) when the other one's danger span (combat.two_play
guard_spans: its jump landing band, its big rune circle, its hammer, its body) meets her way to the stance or the stance
(SP10a / SP10c audits: the stance on one's cast in the other's big rune circle). Done: landed from the hop; the cast over without a
covering bomb; another script took the keys outside the critical window.

    lh = RuneLowHop()                                         # per episode: lh.reset()
    m = lh.step(f, s, ground, accepting, t_game, latch)       # the mask for frame f + 2, or None (the planner decides)
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

import numpy as np

from ssbot.combat import cast_stab as _cs
from ssbot.combat import rune_bombs as _rb
from ssbot.combat import slam_play as _sp


def _on(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip() == "1"


# SP8d A/B (forum.md 75.4; b2c14cd, rnjb vs sp8lh, 16 episodes each, the same seeds: kill p50 21.6 -> 19.5 s, landed / s
# 1.027 -> 1.126 (90 % +0.034 .. +0.165), HP-hitless 16 = 16; the person's rule "the faster arm is the default"): unset,
# SSBOT_FORUM_RUNE_LOWHOP follows SSBOT_FORUM_V2 (on with v2, off without it); =0 turns it off (arm rnsp8d0).
ENABLED = _on("SSBOT_FORUM_RUNE_LOWHOP", "1" if _on("SSBOT_FORUM_V2") else "0")
# SP13b (the person, 2026-10-18 ~08:45: "the runes come from both sides, a big jump would clear both, but Hornet does the
# small hop and gets hit by one side"; SP13's A/B recordings: 123 of 599 two-alive casts had the other Clapper's Cast 2
# 45-90 frames before / after (its cast starts as soon as the first one's lock ends at Cast 2), 43 of them lost HP to a
# small rune vs 34 of the other 476): SSBOT_FORUM_TWO_BOMBS2, default off (=1 on; acts with two Clappers, TWO_CAST).
# The low hop plans against every bomb that covers her from BOTH casters - the bombs seen, the tracker's per-bomb
# forecast (rune_bombs; the rows whose Cast 2 is seen) and the rows still to come (a Clapper in Spell Antic / Cast 1:
# rune_bombs.pending_rows) - with the full jump's holds (17-26: >= 2.95 u for up to 33 frames) when no low hop clears
# them all, and a second hop after landing when one jump cannot (the first covers the earliest windows, the rest must
# stay feasible from its landing); the other one's cast no longer ends / blocks the run (its bombs are in the plan); a
# start also in Cast 1 / Cast 2; once its caster's cast is over the run stays while covering bombs remain (no stance
# walk, the keys only when one is within look2 frames); in the air with a covering bomb soon the umbrella (the jump
# pressed in the air: it holds the height, never lifts) / a drift from the hero model's rollouts against every bomb
# instead of handing back.
# SP13b A/B (f134795, w13, 64 episodes per arm, 2 rounds x 32, block design, the same seeds 9700000.. / 9800000..; rnjb vs
# b2): HP-hitless clears 6 -> 18 / 64 (+0.188, 90 % +0.078 .. +0.297), both killed 42 -> 46 (-5 .. +13), landed / s
# 1.332 -> 1.329 (-0.063 .. +0.057), HP-loss hits / min 3.72 -> 3.02 (-1.43 .. +0.00); small-rune HP losses 22 -> 4,
# overlap pairs clean 21 / 31 -> 30 / 30. The person's rule (the best on hitless clears, not worse on the others):
# BOMBS2 follows SSBOT_FORUM_V2 when unset (on with v2), =0 off (arm rnsp13b_0 = the SP13 default)
BOMBS2 = _on("SSBOT_FORUM_TWO_BOMBS2", "1" if _on("SSBOT_FORUM_V2") else "0")
CLAPPER = _sp.CLAPPER
CAST_ST = ("Spell Antic", "Cast 1", "Cast 2")
M_L, M_R, M_A, M_J = _sp.M_L, _sp.M_R, _sp.M_A, _sp.M_J
SEND_AHEAD = _sp.SEND_AHEAD
WALK_U = _sp.WALK_U
FLOOR = 3.0
HALF_W = 0.25              # her box's half width
HALF_H = 1.0395            # her box's half height (2.079 u)
R = _rb.R
SLASH_X = _sp.SLASH_X      # the side slash's x reach in front of her box centre (0.19 .. 3.12)
# the Wanderer side slash's lower edge (knowledge/1.0.30000/attacks/wanderer.json "normal", the higher of the two
# slashes), x in front of her box centre -> y from her box centre
SLASH_LOW = ((0.193, -0.563), (1.6933, -0.359), (2.8424, -0.0653), (3.1213, 0.298))
# its body (top above the floor, front from its centre) by Control state and state frame (sp8d body_profile)
BODY_IDLE = (3.92, 2.25)
BODY_TALL = (4.78, 1.84)
BODY_LOW = (3.19, 2.05)

# The ground hop: box bottom above the floor on frames j = 0.. after the latched press frame, per hold H (frames), the
# lowest / highest of the kinematics model's timing lanes (sp8d hop_model.py; the logged apex per hold in
# hero_wanderer_forum.json jump_heights agrees: H 11 3.22-3.54, 12 3.54-3.66, 13 3.66-3.94).
HOP_LO = {
    9: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.62, 2.67, 2.67, 2.65, 2.60, 2.60, 2.53, 2.43,
        2.32, 2.17, 2.01, 2.00, 1.81, 1.60, 1.36, 1.10, 0.81, 0.75, 0.49, 0.16, 0.02),
    10: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 2.97, 3.02, 3.02, 3.00, 2.95, 2.91, 2.83,
         2.72, 2.66, 2.52, 2.35, 2.26, 2.05, 1.83, 1.71, 1.45, 1.16, 1.00, 0.68, 0.33, 0.15, 0.02),
    11: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.32, 3.32, 3.33, 3.31, 3.27, 3.21,
         3.12, 3.07, 3.00, 2.87, 2.70, 2.52, 2.31, 2.18, 2.05, 1.79, 1.51, 1.23, 0.91, 0.68, 0.50, 0.12, 0.02),
    12: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.55, 3.55, 3.53, 3.48,
         3.42, 3.42, 3.32, 3.20, 3.06, 2.90, 2.71, 2.61, 2.47, 2.25, 1.99, 1.71, 1.40, 1.19, 0.96, 0.71, 0.32, 0.02),
    13: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.63, 3.67, 3.67, 3.65,
         3.60, 3.60, 3.52, 3.43, 3.30, 3.16, 2.99, 2.99, 2.80, 2.58, 2.34, 2.07, 1.78, 1.67, 1.46, 1.13, 0.77, 0.38,
         0.02),
    14: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 3.92, 3.96, 3.95,
         3.92, 3.87, 3.87, 3.79, 3.69, 3.57, 3.42, 3.25, 3.23, 3.05, 2.83, 2.59, 2.32, 2.03, 1.91, 1.70, 1.37, 1.00,
         0.62, 0.20, 0.02),
    15: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.18, 4.21,
         4.21, 4.17, 4.12, 4.12, 4.04, 3.94, 3.81, 3.66, 3.48, 3.45, 3.28, 3.06, 2.81, 2.54, 2.24, 2.11, 1.91, 1.58,
         1.21, 0.82, 0.41, 0.17, 0.02),
    16: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.42,
         4.45, 4.44, 4.40, 4.34, 4.32, 4.23, 4.12, 4.02, 3.87, 3.69, 3.64, 3.43, 3.20, 3.01, 2.74, 2.44, 2.29, 2.02,
         1.67, 1.40, 1.01, 0.59, 0.33, 0.02),
}
HOP_HI = {
    9: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 2.97, 3.02, 3.02, 3.01, 2.97, 2.91, 2.83, 2.77,
        2.72, 2.59, 2.44, 2.26, 2.06, 1.96, 1.83, 1.58, 1.30, 1.00, 0.75, 0.56, 0.33, 0.02),
    10: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.32, 3.32, 3.33, 3.31, 3.27, 3.21, 3.12,
         3.12, 3.00, 2.87, 2.71, 2.52, 2.40, 2.31, 2.08, 1.82, 1.54, 1.23, 1.10, 0.91, 0.55, 0.17, 0.02),
    11: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.55, 3.55, 3.53, 3.48, 3.42,
         3.42, 3.32, 3.20, 3.06, 2.90, 2.71, 2.71, 2.49, 2.25, 2.05, 1.79, 1.51, 1.40, 1.06, 0.71, 0.50, 0.12, 0.02),
    12: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.63, 3.67, 3.67, 3.67, 3.65,
         3.60, 3.52, 3.43, 3.37, 3.30, 3.16, 2.99, 2.80, 2.61, 2.47, 2.34, 2.07, 1.78, 1.47, 1.19, 0.96, 0.77, 0.38,
         0.02),
    13: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 3.92, 3.96, 3.96, 3.95,
         3.92, 3.87, 3.79, 3.70, 3.64, 3.57, 3.42, 3.25, 3.05, 2.88, 2.73, 2.59, 2.32, 2.03, 1.71, 1.46, 1.22, 1.00,
         0.62, 0.20, 0.02),
    14: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.18, 4.21, 4.21,
         4.21, 4.17, 4.12, 4.04, 3.95, 3.90, 3.81, 3.66, 3.48, 3.28, 3.13, 2.98, 2.81, 2.54, 2.24, 1.93, 1.70, 1.46,
         1.21, 0.82, 0.41, 0.02),
    15: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.42, 4.45,
         4.45, 4.43, 4.39, 4.32, 4.23, 4.19, 4.12, 3.98, 3.82, 3.64, 3.45, 3.35, 3.20, 2.94, 2.66, 2.35, 2.11, 1.91,
         1.67, 1.29, 0.89, 0.47, 0.17, 0.02),
    16: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.55, 4.64,
         4.64, 4.64, 4.61, 4.56, 4.49, 4.41, 4.39, 4.27, 4.12, 3.95, 3.76, 3.65, 3.54, 3.30, 3.03, 2.75, 2.44, 2.29,
         2.09, 1.73, 1.40, 1.01, 0.59, 0.02),
}
# SP13b (SSBOT_FORUM_TWO_BOMBS2): the full jump's holds 17-26 from the same model (C:/ssbot/data/m2_play/sp13b/
# hop_ext.json, scripts/hop_ext.py; holds 12 / 16 reproduce the lo lanes above exactly): the apex 4.64 (H 17) - 5.48 u
# (H 26), the box bottom >= 2.95 u from j 11 to j 32 (H 17) - 43 (H 26) against 11 - 31 for the low hops
HOP_LO.update({
    17: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.55,
        4.64, 4.64, 4.64, 4.61, 4.55, 4.49, 4.39, 4.32, 4.22, 4.06, 3.88, 3.76, 3.54, 3.39, 3.19, 2.91, 2.61, 2.43,
        2.09, 1.86, 1.56, 1.16, 0.74, 0.47, 0.05, 0.01),
    18: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.55,
        4.75, 4.75, 4.78, 4.77, 4.73, 4.67, 4.59, 4.57, 4.49, 4.35, 4.20, 4.02, 3.82, 3.70, 3.56, 3.34, 3.06, 2.76,
        2.45, 2.24, 2.02, 1.70, 1.30, 0.88, 0.47, 0.18, 0.01),
    19: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.55,
        4.75, 4.75, 4.83, 4.84, 4.83, 4.79, 4.72, 4.72, 4.63, 4.52, 4.38, 4.22, 4.04, 3.97, 3.83, 3.60, 3.34, 3.06,
        2.76, 2.58, 2.36, 2.08, 1.70, 1.30, 0.88, 0.59, 0.29, 0.01),
    20: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.55,
        4.75, 4.75, 4.93, 5.00, 5.01, 4.99, 4.94, 4.88, 4.88, 4.78, 4.67, 4.53, 4.37, 4.18, 4.09, 3.96, 3.73, 3.47,
        3.19, 2.88, 2.69, 2.46, 2.19, 1.81, 1.41, 0.98, 0.68, 0.37, 0.06, 0.02),
    21: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.55,
        4.75, 4.75, 4.93, 5.09, 5.14, 5.14, 5.12, 5.07, 5.00, 5.00, 4.91, 4.79, 4.65, 4.48, 4.29, 4.19, 4.05, 3.84,
        3.58, 3.29, 2.98, 2.77, 2.54, 2.29, 1.90, 1.50, 1.07, 0.75, 0.43, 0.13, 0.02),
    22: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.55,
        4.75, 4.75, 4.93, 5.09, 5.22, 5.26, 5.26, 5.23, 5.18, 5.10, 5.10, 5.01, 4.88, 4.74, 4.56, 4.37, 4.26, 4.11,
        3.91, 3.64, 3.35, 3.04, 2.83, 2.59, 2.33, 1.95, 1.54, 1.10, 0.80, 0.47, 0.16, 0.02),
    23: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.55,
        4.75, 4.75, 4.93, 5.09, 5.22, 5.33, 5.36, 5.35, 5.31, 5.26, 5.18, 5.15, 5.03, 4.94, 4.79, 4.61, 4.41, 4.30,
        4.11, 3.94, 3.67, 3.37, 3.05, 2.85, 2.59, 2.33, 1.94, 1.52, 1.08, 0.79, 0.47, 0.13, 0.02),
    24: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.55,
        4.75, 4.75, 4.93, 5.09, 5.22, 5.33, 5.41, 5.41, 5.41, 5.37, 5.31, 5.22, 5.16, 5.09, 4.98, 4.82, 4.64, 4.43,
        4.30, 4.15, 3.94, 3.67, 3.36, 3.04, 2.85, 2.62, 2.31, 1.91, 1.49, 1.04, 0.79, 0.48, 0.07, 0.02),
    25: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.55,
        4.75, 4.75, 4.93, 5.09, 5.22, 5.33, 5.41, 5.41, 5.43, 5.41, 5.37, 5.31, 5.22, 5.19, 5.11, 4.98, 4.82, 4.64,
        4.43, 4.30, 4.17, 3.93, 3.64, 3.33, 3.04, 2.82, 2.62, 2.26, 1.86, 1.43, 1.04, 0.73, 0.47, 0.02),
    26: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.55,
        4.75, 4.75, 4.93, 5.09, 5.22, 5.33, 5.41, 5.41, 5.47, 5.48, 5.46, 5.41, 5.34, 5.25, 5.19, 5.11, 4.96, 4.79,
        4.64, 4.42, 4.28, 4.12, 3.85, 3.56, 3.33, 3.00, 2.76, 2.53, 2.14, 1.73, 1.43, 0.97, 0.65, 0.34, 0.02),
})
HOP_HI.update({
    17: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.55, 4.75,
        4.75, 4.78, 4.77, 4.73, 4.67, 4.59, 4.59, 4.49, 4.35, 4.22, 4.06, 3.88, 3.82, 3.59, 3.39, 3.19, 2.91, 2.61,
        2.45, 2.10, 1.86, 1.56, 1.16, 0.74, 0.47, 0.05),
    18: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.55, 4.75,
        4.75, 4.83, 4.84, 4.84, 4.83, 4.79, 4.72, 4.63, 4.57, 4.50, 4.38, 4.22, 4.04, 3.83, 3.70, 3.56, 3.34, 3.06,
        2.76, 2.45, 2.24, 2.02, 1.70, 1.30, 0.88, 0.47, 0.18),
    19: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.55, 4.75,
        4.75, 4.93, 5.00, 5.01, 5.01, 4.99, 4.94, 4.88, 4.78, 4.72, 4.66, 4.53, 4.37, 4.18, 3.97, 3.84, 3.71, 3.47,
        3.19, 2.88, 2.58, 2.36, 2.16, 1.81, 1.41, 0.98, 0.59, 0.29),
    20: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.55, 4.75,
        4.75, 4.93, 5.09, 5.14, 5.14, 5.14, 5.12, 5.07, 5.00, 4.91, 4.85, 4.79, 4.65, 4.48, 4.29, 4.09, 3.96, 3.83,
        3.58, 3.29, 2.98, 2.69, 2.46, 2.28, 1.90, 1.50, 1.07, 0.68, 0.37, 0.12),
    21: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.55, 4.75,
        4.75, 4.93, 5.09, 5.22, 5.26, 5.26, 5.26, 5.23, 5.18, 5.10, 5.01, 4.95, 4.88, 4.74, 4.56, 4.37, 4.19, 4.05,
        3.91, 3.64, 3.35, 3.04, 2.77, 2.54, 2.33, 1.95, 1.54, 1.10, 0.75, 0.43, 0.16),
    22: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.55, 4.75,
        4.75, 4.93, 5.09, 5.22, 5.33, 5.36, 5.36, 5.34, 5.30, 5.24, 5.15, 5.10, 5.03, 4.90, 4.74, 4.56, 4.37, 4.26,
        4.11, 3.91, 3.64, 3.35, 3.04, 2.83, 2.59, 2.33, 1.95, 1.54, 1.10, 0.80, 0.47, 0.16),
    23: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.55, 4.75,
        4.75, 4.93, 5.09, 5.22, 5.33, 5.41, 5.41, 5.41, 5.38, 5.33, 5.26, 5.18, 5.16, 5.03, 4.94, 4.79, 4.61, 4.41,
        4.30, 4.11, 3.94, 3.67, 3.37, 3.05, 2.85, 2.59, 2.33, 1.94, 1.52, 1.08, 0.79, 0.47, 0.13),
    24: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.55, 4.75,
        4.75, 4.93, 5.09, 5.22, 5.33, 5.41, 5.41, 5.43, 5.43, 5.41, 5.37, 5.31, 5.22, 5.16, 5.09, 4.98, 4.82, 4.64,
        4.43, 4.30, 4.15, 3.94, 3.67, 3.36, 3.04, 2.85, 2.62, 2.31, 1.91, 1.49, 1.04, 0.79, 0.48, 0.07),
    25: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.55, 4.75,
        4.75, 4.93, 5.09, 5.22, 5.33, 5.41, 5.41, 5.47, 5.48, 5.48, 5.46, 5.41, 5.34, 5.25, 5.19, 5.12, 4.99, 4.83,
        4.64, 4.43, 4.30, 4.17, 3.93, 3.64, 3.33, 3.04, 2.82, 2.62, 2.26, 1.86, 1.43, 1.04, 0.73, 0.47),
    26: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.55, 4.75,
        4.75, 4.93, 5.09, 5.22, 5.33, 5.41, 5.41, 5.47, 5.51, 5.51, 5.50, 5.47, 5.42, 5.34, 5.25, 5.19, 5.11, 4.96,
        4.79, 4.64, 4.42, 4.28, 4.12, 3.85, 3.56, 3.33, 3.00, 2.76, 2.53, 2.14, 1.73, 1.43, 0.97, 0.65, 0.34),
})


@dataclass
class HopCfg:
    stand_lo: float = 3.6        # the stance from its centre (u, centre to centre): walk out when nearer
    stand_hi: float = 4.6        # ... walk in when farther (its tall body's front 1.84 + the reach 3.12 - spare)
    x0_lo: float = 2.95          # from Cast 2 on, her x from x0 (its x at the Cast 2 entry): ring 0 reaches < 2.67
    x0_hi: float = 5.45          # ... ring 2 reaches > 5.73
    margin: float = 0.12         # u: her box bottom at least this above the bomb circle's top at her box's nearest x
    pre: int = 1                 # frames before the earliest predicted first lit frame ...
    post: int = 1                # ... and after the latest predicted last lit frame, also clear
    lead_lo: int = 20            # a bomb lights this many game frames after it appears (p5)
    lead_hi: int = 21            # ... (p95)
    dur: int = 7                 # lit frames at most (p95; p50 6)
    x_pad: float = 0.3           # a bomb covers her when |her x - its x| < R + her half width + this
    h_min: int = 9
    h_max: int = 16
    min_slack: int = 3           # a hold needs at least this many press frames that clear (else the next hold)
    slash_cd: int = 19           # own presses this many frames apart (the Wanderer cooldown 0.3 s = 18 + 1)
    reach_spare: float = 0.1     # the slash's x reach must overlap its body box by this much
    y_spare: float = 0.1         # ... and its lower edge must be this much below the body's top
    start_max: float = 10.5      # no start farther than this at the antic entry (u; walking in from there
    #                              reaches the band by antic frame ~44)
    gap_lo: float = 0.6          # in the air: no key toward it when her box centre is nearer its body's edge than
    #                              this (u) ...
    gap_hi: float = 2.0          # ... the key toward it when the gap is beyond this (t1, 5c7cbd8, gap_hi 2.6: the
    #                              descent's slash at j 24 met its Idle body from d <= 4.63 u in 9 of 9, from 4.64 on
    #                              in 2 of 14 - its evade starts then)
    k_max: int = 200             # the run ends this many frames after the antic entry at the latest
    land_wait: int = 50          # after the press: no landing by P + this -> hand back
    cast2_k: float = 49.5        # Cast 2 entry from the antic entry (p50; before it is seen)
    cast2_len: int = 24          # Cast 2's frames (its Idle from C + 24, p5)
    # ---- SP13b SSBOT_FORUM_TWO_BOMBS2 (act only with it on) ----
    h_max2: int = 26             # the full jump's holds up to this (the apex 5.48 u at 26; a longer hold adds nothing)
    look2: int = 45              # free mode (its caster's cast over): the keys only while a covering bomb's window
    #                              starts within this many frames (else the other scripts / the planner)
    rise2: int = 13              # a second hop needs its press this many frames before its first window (j 12: 2.95 u)
    air2: int = 1                # in the air with a covering bomb soon: the hero model's umbrella / drift plans
    air_m: float = 0.35          # ... her box this clear of every lit bomb circle (the model floats 0.2 - 0.3 u high:
    #                              SP11a float_check)
    air_h: int = 70              # ... the rollout horizon (frames)


def _num_env(c: HopCfg) -> HopCfg:
    """SSBOT_FORUM_RUNE_LOWHOP_SET="margin=0.15,stand_hi=4.4": trial overrides of the numbers above."""
    for kv in os.environ.get("SSBOT_FORUM_RUNE_LOWHOP_SET", "").replace(";", ",").split(","):
        if "=" not in kv:
            continue
        k, v = (x.strip() for x in kv.split("=", 1))
        if not hasattr(c, k):
            raise KeyError(f"SSBOT_FORUM_RUNE_LOWHOP_SET: unknown key {k!r}")
        cur = getattr(c, k)
        setattr(c, k, type(cur)(float(v)))
    return c


def slash_low(g: float) -> float:
    """The side slash's lower edge (y from her box centre) at x g in front of her box centre."""
    g = max(g, SLASH_LOW[0][0])
    for (x0, y0), (x1, y1) in zip(SLASH_LOW, SLASH_LOW[1:]):
        if g <= x1:
            return y0 + (y1 - y0) * (g - x0) / (x1 - x0)
    return SLASH_LOW[-1][1]


def bomb_top(by: float, dx: float) -> float:
    """The top of a bomb circle (centre y by) above the floor at her box's nearest x (her box centre dx from its
    centre); -inf when her box is clear of it sideways."""
    e = max(0.0, abs(dx) - HALF_W)
    if e >= R:
        return -math.inf
    return by + math.sqrt(R * R - e * e) - FLOOR


def body_at(st: str | None, kst: float) -> tuple[float, float]:
    """(top above the floor, front from its centre) of its body box in Control state st at state frame kst."""
    if st == "Spell Antic":
        return BODY_LOW if kst < 4 else ((4.36, 2.06) if kst < 8 else BODY_TALL)
    if st == "Cast 1":
        return BODY_TALL
    if st == "Cast 2":
        return BODY_TALL if kst < 14 else BODY_LOW
    return BODY_IDLE


def hop_plan(threats: list[tuple[int, int, float]], k_first: int, holds: range, min_slack: int, score=None
             ) -> dict | None:
    """The hop for threats [(w0, w1, thr)]: game frames w0 .. w1 (k) that need her box bottom >= thr (above the
    floor). Press frames P >= k_first. The lowest hold with >= min_slack clearing press frames (else the lowest with
    any): {"H", "P", "lo", "hi"} (lo .. hi the clearing presses), P the best by score(H, P) (higher better; ties: the
    middle), or None."""
    fallback = None
    for H in holds:
        lo_t = HOP_LO[H]
        ok = []
        for P in range(k_first, k_first + 60):
            good = True
            for w0, w1, thr in threats:
                j0, j1 = w0 - P, w1 - P
                if j0 < 0 or j1 >= len(lo_t) or any(lo_t[j] < thr for j in range(j0, j1 + 1)):
                    good = False
                    break
            if good:
                ok.append(P)
            elif ok:
                break
        if not ok:
            continue
        mid = 0.5 * (ok[0] + ok[-1])
        if score is not None:
            best = max(ok, key=lambda P: (score(H, P), -abs(P - mid)))
        else:
            best = min(ok, key=lambda P: abs(P - mid))
        plan = {"H": H, "P": int(best), "lo": ok[0], "hi": ok[-1]}
        if len(ok) >= min_slack:
            return plan
        if fallback is None:
            fallback = plan
    return fallback


def hop_plan2(threats: list[tuple[int, int, float]], k_first: int, holds: range, min_slack: int, score=None,
              rise: int = 13) -> dict | None:
    """(SP13b BOMBS2) the first hop against every covering window [(w0, w1, thr)]: the lowest hold that clears them all
    (hop_plan over the full holds), else the longest run of the earliest windows one hop clears whose remaining windows
    a second hop pressed after its landing still clears (its press >= the landing + 1 and its first window >= its press
    + rise); else (tail=True) the longest run of the earliest windows one hop clears, H2 -1: the rest is left to the
    umbrella in the air (RuneLowHop._air_plan). {"H", "P", "lo", "hi", "n", "of", "H2"} or None."""
    ts = sorted(threats)
    tail = None
    for n in range(len(ts), 0, -1):
        first, rest = ts[:n], ts[n:]
        plan = hop_plan(first, k_first, holds, min_slack, score=score)
        if plan is None:
            continue
        plan["w_end"] = max(w1 for _, w1, _ in first)
        if not rest:
            return {**plan, "n": n, "of": len(ts), "H2": None}
        if tail is None:
            tail = {**plan, "n": n, "of": len(ts), "H2": -1}
        land = plan["P"] + len(HOP_LO[plan["H"]])
        w_rest = min(w0 for w0, _, _ in rest)
        if w_rest < land + 1 + rise:
            continue
        if w_rest >= land + 1 + 50:
            return {**plan, "n": n, "of": len(ts), "H2": 0}     # the rest is far: planned after the landing
        p2 = hop_plan2(rest, land + 1, holds, 1, rise=rise)
        if p2 is not None and p2["n"] == p2["of"]:
            return {**plan, "n": n, "of": len(ts), "H2": p2["H"]}
    return tail


@dataclass
class Hop:
    iid: object
    face: int                    # its facing (+1 right); she is in front of it
    f0: int                      # the STATE frame of the start
    ta: float                    # the antic entry on the clock (s)
    fa: int                      # the antic entry's STATE frame (f0 - its state time)
    d0: float                    # her x in front of its centre at the start (u)
    ground0: bool
    hp0: int
    phase: str = "stance"        # stance -> hop -> done / abort
    why: str = ""
    tc: float | None = None      # the Cast 2 entry on the clock
    x0: float | None = None      # its x at the Cast 2 entry (ring 0's x once seen)
    bombs: dict = field(default_factory=dict)    # entity iid -> {"x", "y", "a", "on", "off", "end"}
    plan: dict | None = None     # the hop being planned / committed
    P: int | None = None         # the committed press frame (k) and hold
    H: int | None = None
    k_land: int | None = None
    presses: list = field(default_factory=list)  # (k of the mask, air?, her x in front, predicted bottom)
    hits: list = field(default_factory=list)     # (k, src)
    sent: list = field(default_factory=list)     # (f, mask)
    ticks: int = 0
    k: int = 0
    late: int = 0                # ticks a covering bomb was due with no feasible hop
    plans: int = 0
    # SP13b BOMBS2
    fcw: list = field(default_factory=list)     # the forecast's covering windows of the last tick [(w0, w1, thr)]
    free: int = 0                # ticks in free mode (its caster's cast over, covering bombs left)
    rehop: int = 0               # back to the stance after a landing with covering bombs left
    big: int = 0                 # hops with a hold > 16 (the full jump)
    split: int = 0               # plans with a second hop after the landing
    air: list = field(default_factory=list)     # in-air plans used: (k, kind)
    owners: set = field(default_factory=set)    # the casters whose bombs covered her
    # SP13b TWO_PMCAST (the cast route of TWO_PUSHMID: the over plan instead of the hop)
    pm: int | None = None        # the world side to cross to (F's wall side) while the route is due
    pm_why: str = ""             # how the route ended (over / no plan / ...)
    op: object = None            # the over plan (rune_pogo.Plan, absolute mask frames)
    op_plans: int = 0            # over searches
    op_ms: float = 0.0           # their time (ms)
    op_k: int | None = None      # the antic frame of the jump press (committed)
    op_j0: int | None = None     # its mask frame
    op_bounce: int | None = None  # the mask frame the bounce off F's head was seen
    op_guard: int = 0            # ticks the landing guard steered her off F's body
    op_fail: int = 0             # ticks the committed plan failed its check
    op_alt: int = 0              # in-air replacements (best_air)


class RuneLowHop:
    def __init__(self, cfg: HopCfg | None = None, two: bool = False):
        self.cfg = cfg or _num_env(HopCfg())
        # SP9a S3 (SSBOT_FORUM_TWO_CAST, combat.two_play): with two live Clappers the caster in Spell Antic nearest to
        # her in front; no start / hand back (outside the critical window) while the other one can reach her
        self.two = two
        if two:
            from ssbot.combat import two_play as _tp
            self._stance_body_pad = (_tp._guard_cfg() if _tp.GUARD else _tp.GuardCfg()).body_pad
        self.run: Hop | None = None
        self.done: list[Hop] = []
        self._seen: set = set()
        self.n_cast = 0
        self.why_not: dict = {}
        self._runes: dict = {}
        self.guard_f: list = []            # SSBOT_FORUM_TWO_GUARD: frames of the casts not started for it
        self.b2 = BOMBS2 and two           # SP13b: both casters' bombs (forecast) in the plan
        from ssbot.combat import push_cast as _pc
        self.pmc = _pc.PMCAST              # SP13b TWO_PMCAST: the over plan on the cast route's F
        self.pccfg = _pc.cfg_from_env() if self.pmc else _pc.PcCfg()
        self._pm: dict = {}                # this tick's cast-route requests (TwoPlay.pm_cast: F's iid -> wdir)
        self.pm_giveup: str | None = None  # the route given up this tick (the policy tells TwoPlay)
        self._bk = None                    # BOMBS2: this tick's forecast rows (rune_bombs.frames, from the STATE)
        self._sim = None                   # BOMBS2: this tick's hero model (air_chain.ChainSim) for the air plans

    def reset(self) -> None:
        self.run = None
        self.done = []
        self._seen = set()
        self.n_cast = 0
        self.why_not = {}
        self._runes = {}
        self.guard_f = []

    # ---- bookkeeping ----

    def observe(self, f: int, s: dict) -> None:
        """Every tick (whichever script runs): the jump cast rune circles' first frame and lit state."""
        self._rune_threats(f, s)

    def _rune_threats(self, f: int, s: dict) -> list[tuple[float, float]]:
        out = []
        for lo, hi, iid, lit in _cs.rune_spans(s):
            r = self._runes.setdefault(iid, {"first": f, "lit": False})
            if lit:
                r["lit"] = True
                out.append((lo, hi))
            elif not r["lit"] and f - r["first"] < _cs.RUNE_LIVE_F:
                out.append((lo, hi))
        return out

    def active(self) -> bool:
        return self.run is not None and self.run.phase in ("stance", "hop", "over")

    def critical(self) -> bool:
        """The hop's hold or a covering bomb's window is on: the script keeps the keys ahead of the other scripts."""
        r = self.run
        if r is not None and r.phase == "over":
            return True                                   # (SP13b TWO_PMCAST) the over plan holds the keys
        if r is None or r.phase != "hop" or r.P is None:
            return False
        if r.k < r.P + r.H + 1:
            return True
        if self.b2 and any(w0 <= r.k + 2 and w1 >= r.k for w0, w1, _ in r.fcw):
            return True
        return any(w1 >= r.k for _, w1, _ in self._threat_windows(r, None))

    def abort(self, why: str) -> None:
        if self.active():
            self._close("abort", why)

    def yield_to(self, s: dict) -> None:
        """Another script sends the keys this tick (outside the critical window): the run ends."""
        if self.active():
            self._close("done", "other")

    def _close(self, phase: str, why: str = "") -> None:
        r = self.run
        if r is not None:
            r.phase, r.why = phase, r.why or why
            self.done.append(r)
        self.run = None

    def stats(self) -> dict:
        from collections import Counter
        out = Counter({"casts": self.n_cast})
        runs = self.done + ([self.run] if self.run is not None else [])
        for r in runs:
            out["runs"] += 1
            out["hops"] += r.P is not None
            out["presses"] += len(r.presses)
            out["air_presses"] += sum(1 for p in r.presses if p[1])
            out["hits_in_run"] += len(r.hits)
            out["late"] += r.late > 0
            out[f"end_{r.phase}_{r.why}"] += 1
            if r.H is not None:
                out[f"hold_{r.H}"] += 1
            if self.pmc and (r.pm is not None or r.pm_why):
                out["pm_runs"] += 1
                out[f"pm_end_{r.pm_why or 'open'}"] += 1
                out["pm_over"] += r.op_k is not None
            if self.b2:
                out["b2_free_ticks"] += r.free
                out["b2_rehop"] += r.rehop
                out["b2_big"] += r.big
                out["b2_split"] += r.split
                out["b2_air"] += len(r.air)
                out["b2_two_owner_runs"] += len(r.owners) >= 2
        for k, v in self.why_not.items():
            out[f"no_{k}"] += v
        res = dict(out)
        res["hop_runs"] = [self._rec(r) for r in runs]
        if self.guard_f:
            res["guard_nostart_f"] = list(self.guard_f)
        return res

    @staticmethod
    def _rec(r: Hop) -> dict:
        return {"f0": r.f0, "fa": r.fa, "d0": r.d0, "ground0": r.ground0, "x0": r.x0,
                "k_c2": None if r.tc is None else round((r.tc - r.ta) * 60.0, 1),
                "bombs": {str(i): b for i, b in r.bombs.items() if b.get("cover")},
                "plan": r.plan, "P": r.P, "H": r.H, "k_land": r.k_land, "presses": r.presses, "hits": r.hits,
                "late": r.late, "plans": r.plans, "end": r.phase, "why": r.why, "ticks": r.ticks, "k": r.k,
                **({"b2": {"free": r.free, "rehop": r.rehop, "big": r.big, "split": r.split, "air": r.air,
                           "owners": sorted(str(o) for o in r.owners), "iid": str(r.iid)}} if BOMBS2 else {}),
                **({"pm": {"dir": r.pm, "why": r.pm_why, "k_jump": r.op_k, "plans": r.op_plans,
                           "ms": round(r.op_ms, 1), "fail": r.op_fail, "alt": r.op_alt, "guard": r.op_guard,
                           "bounce": r.op_bounce,
                           "plan": None if r.op is None else [r.op.jump, r.op.d0, r.op.d1, r.op.press, r.op.contact,
                                                              r.op.umb, r.op.why]}}
                   if (r.pm is not None or r.pm_why) else {})}

    # ---- the script ----

    def step(self, f: int, s: dict, ground: bool, accepting: bool = True, t_game: float | None = None,
             latch=None, skip: frozenset | None = None, guard: list | None = None, bombs=None,
             sim=None, pm: dict | None = None) -> int | None:
        """The mask for frame f + 2 while the script runs, else None. t_game: the game clock (s; Stamp.t_game_s);
        latch: m -> the key mask the oracle's hold filter latches at f + 2 when m is sent for it (None: m).
        (SP13b BOMBS2) bombs: the tracker's per-bomb forecast (rune_bombs.frames rows from this STATE; the rows still
        to come are added here), sim: the tick's hero model (air_chain.ChainSim) for the air plans."""
        t = f / 60.0 if t_game is None else float(t_game)
        self._pm = pm or {}
        self.pm_giveup = None
        if self.b2 or self._pm or (self.run is not None and self.run.phase == "over"):
            pend = _rb.pending_rows([(x.get("iid"), float(x["pos"][0]), float(x["pos"][1]), *_sp.control(x))
                                     for x in _sp.clappers(s)])
            fc = np.asarray(bombs, float).reshape(-1, 6) if bombs is not None and len(bombs) else np.zeros((0, 6))
            self._bk = np.concatenate([fc, pend]) if len(pend) else fc
            self._sim = sim
        e = self._pick(s) if self.two else _sp.clapper(s)
        if skip and e is not None and e.get("iid") in skip and not self.critical():
            # SP9c (combat.two_play's antic switch): its cast is left alone (she switched to the other one)
            if self.run is not None and self.run.iid in skip:
                self._close("abort", "asw")
            return None
        st, tin = _sp.control(e)
        h = s.get("hero") or {}
        hp = int(h.get("health") or 0)
        r = self.run
        if r is not None:
            if hp < r.hp0:
                self._close("abort", "hurt")
                return None
            gone = e is None or e.get("iid") != r.iid
            two = not gone and not self._n_ok(s)
            new = not gone and st == "Spell Antic" and abs((t - tin) - r.ta) * 60.0 > 30
            if (gone or two or new) and self.critical():
                # t1 (5c7cbd8): an air slash killed it at P + 7, the run ended, the hold was cut at 8 frames and its
                # ring-1 bomb (the bombs stay) hit her 7 frames later: the hold and the bomb window run on
                r.k = int(round((t - r.ta) * 60.0)) + SEND_AHEAD
                self._observe_cast(r, s, None, None, 0.0, t, r.k - SEND_AHEAD)
                if r.phase == "over":
                    return self._over_step(r, f, s, None, ground)     # (SP13b) the over plan runs on
                m = M_J if r.k - r.P < r.H else 0
                r.sent.append((f, m))
                r.ticks += 1
                r.why = r.why or ("gone (hop on)" if gone else "two (hop on)" if two else "new cast (hop on)")
                return m
            if gone:
                self._close("abort", "gone")
                return None
            if two:
                self._close("abort", "two")
                return None
            if new:
                self._close("done", "new cast")          # a new cast: its own run below
                r = None
            elif self.two and len(_sp.clappers(s)) == 2 and not self.critical():
                from ssbot.combat import two_play as _tp
                why = _tp.other_danger(s, r.iid, self._hx(s), cast_ok=self.b2)
                if why is not None:
                    self._close("abort", "other")
                    return None
                if self._stance_in_other_body(s, e, r.face):
                    self._close("abort", "other body")
                    return None
                if guard is not None and e is not None and self._guarded(s, e, r.face, guard):
                    self._close("abort", "guard")
                    return None
        if r is None:
            if e is None or st not in (CAST_ST if self.b2 else ("Spell Antic",)):
                return None
            # (SP13b BOMBS2) a start in Cast 1 / Cast 2 too: its antic entry from the p50 timeline
            ta = t - tin - (0.0 if st == "Spell Antic" else (43.5 if st == "Cast 1" else self.cfg.cast2_k) / 60.0)
            key = (e.get("iid"), round(ta * 60.0))
            if any(k_[0] == key[0] and abs(k_[1] - key[1]) <= 3 for k_ in self._seen):
                return None
            self._seen.add(key)
            self.n_cast += 1
            face = 1 if e.get("flipX") else -1
            d0 = (_sp.hero_x(s) - float(e["pos"][0])) * face
            why = None
            if not self._n_ok(s):
                why = "two"
            elif d0 <= 0:
                why = "behind"
            elif d0 > self.cfg.start_max:
                why = "far"
            elif hp <= 0:
                why = "dead"
            elif self._rune_over(f, s, float(e["pos"][0]), face):
                why = "rune"
            elif self.two and len(_sp.clappers(s)) == 2:
                from ssbot.combat import two_play as _tp
                if _tp.other_danger(s, e.get("iid"), self._hx(s), cast_ok=self.b2) is not None:
                    why = "other"
                elif self._stance_in_other_body(s, e, face):
                    why = "other body"
                elif guard is not None and self._guarded(s, e, face, guard):
                    why = "guard"
                    self.guard_f.append(f)          # SSBOT_FORUM_TWO_GUARD: the no-start frames (stats)
            if why is not None:
                self.why_not[why] = self.why_not.get(why, 0) + 1
                return None
            r = self.run = Hop(iid=e.get("iid"), face=face, f0=f, ta=ta, fa=int(f - round(tin * 60.0)),
                               d0=round(d0, 3), ground0=bool(ground), hp0=hp)
        k_now = int(round((t - r.ta) * 60.0))
        r.k = k_now + SEND_AHEAD
        if self.pmc and r.pm is None and not r.pm_why and r.iid in self._pm and r.phase == "stance":
            r.pm = int(self._pm[r.iid])                   # (SP13b TWO_PMCAST) the cast route on this cast
        self._observe_cast(r, s, e, st, tin, t, k_now)
        for ev in s.get("ev") or ():
            d = ev.get("d") or {}
            if ev.get("k") == "hit" and d.get("type_key") == CLAPPER:
                dealt = d.get("dealt", d.get("amount"))
                if dealt is None or float(dealt) > 0:
                    r.hits.append((k_now, str(d.get("src"))))
        m = self._step(r, f, s, e, st, tin, ground, accepting, latch)
        if m is None:
            return None
        r.sent.append((f, m))
        r.ticks += 1
        return m

    def _n_ok(self, s: dict) -> bool:
        n = len(_sp.clappers(s))
        return n == 1 or (n == 2 and self.two)

    def _pick(self, s: dict) -> dict | None:
        """two=True: the run's Clapper; else (two live) the one in Spell Antic nearest to her with her in front; else
        the first."""
        cs = _sp.clappers(s)
        if self.run is not None:
            return next((e for e in cs if e.get("iid") == self.run.iid), None)
        if len(cs) == 2:
            hx = _sp.hero_x(s)
            sp_ = [e for e in cs if _sp.control(e)[0] == "Spell Antic"
                   and (hx - float(e["pos"][0])) * (1 if e.get("flipX") else -1) > 0]
            if sp_:
                return min(sp_, key=lambda e: abs(float(e["pos"][0]) - hx))
            if self.b2:
                # (SP13b BOMBS2) a caster in Cast 1 / Cast 2 in front (a start there)
                c12 = [e for e in cs if _sp.control(e)[0] in ("Cast 1", "Cast 2")
                       and (hx - float(e["pos"][0])) * (1 if e.get("flipX") else -1) > 0]
                if c12:
                    return min(c12, key=lambda e: abs(float(e["pos"][0]) - hx))
        return _sp.clapper(s)

    def _stance_in_other_body(self, s: dict, e: dict, face: int) -> bool:
        """Destination band only; independent of guard.low, never a path check."""
        from ssbot.combat import two_play as _tp
        try:
            cx = float(e["pos"][0]) + float((e.get("vel") or [0., 0.])[0]) * SEND_AHEAD / 60.
            a, b = sorted((cx + face * self.cfg.stand_lo, cx + face * self.cfg.stand_hi))
            pad = self._stance_body_pad
            if not all(math.isfinite(v) for v in (a, b, pad)) or pad < 0:
                return True
            for other in _sp.clappers(s):
                if other.get("iid") == e.get("iid"):
                    continue
                lo, hi = _tp.body_span(other)
                if not all(math.isfinite(v) for v in (lo, hi)) or lo >= hi:
                    return True
                if lo - pad < b and hi + pad > a:
                    return True
            return False
        except (KeyError, TypeError, ValueError, OverflowError):
            return True

    def _guarded(self, s: dict, e: dict, face: int, guard: list) -> str | None:
        """SSBOT_FORUM_TWO_GUARD: the other Clapper's danger span kind over her way to the stance or the stance."""
        from ssbot.combat import two_play as _tp
        cx = float(e["pos"][0])
        a, b = cx + face * self.cfg.stand_lo, cx + face * self.cfg.stand_hi
        hx = _sp.hero_x(s)
        # (fp1 fix, 3251a4a: 4 of 9 guard no-starts / aborts lost HP, 2 of them to the very bombs the hop is for) only
        # the other one's big rune circle (SP10a / SP10c: the stance in it); its hammer / cast stay other_danger's
        return _tp.guard_hit(guard, min(a, b, hx), max(a, b, hx), kinds=("rune",), own=e.get("iid"))

    def _rune_over(self, f: int, s: dict, cx: float, face: int) -> bool:
        a = cx + face * self.cfg.stand_lo
        b = cx + face * self.cfg.stand_hi
        hx = _sp.hero_x(s)
        lo, hi = min(a, b, hx), max(a, b, hx)
        return any(x < hi and y > lo for x, y in self._rune_threats(f, s))

    def _observe_cast(self, r: Hop, s: dict, e: dict, st: str | None, tin: float, t: float, k_now: int) -> None:
        if st == "Cast 2" and r.tc is None and e is not None:
            r.tc = t - tin
            if r.x0 is None:
                r.x0 = float(e["pos"][0])
        cur = {}
        for iid, bx, by, lit in _rb.bomb_ents(s.get("ents")):
            cur[iid] = lit
            b = r.bombs.get(iid)
            if b is not None and abs(b["x"] - bx) > 0.3:
                b = None                                    # a pooled object placed anew
            if b is None:
                b = r.bombs[iid] = {"x": round(bx, 3), "y": round(by, 3), "a": k_now, "on": None, "off": None,
                                    "end": False}
                if r.x0 is not None and abs(bx - r.x0) < 0.6 and (r.tc is not None and k_now <= (r.tc - r.ta) * 60
                                                                  + 3):
                    r.x0 = float(bx)                        # ring 0: the exact x0
            if lit:
                if b["on"] is None:
                    b["on"] = k_now
                b["off"] = k_now
            elif b["on"] is not None:
                b["end"] = True
        for iid, b in r.bombs.items():
            # gone after it lit: spent; gone unlit (the pool may drop it for a frame or two): spent only once its
            # latest lit window is past
            if iid not in cur and (b["on"] is not None or k_now > b["a"] + self.cfg.lead_hi + self.cfg.dur + 2):
                b["end"] = True

    def _hx(self, s: dict) -> float:
        h = s.get("hero") or {}
        vx = float((h.get("vel") or [0.0, 0.0])[0])
        return _sp.hero_x(s) + vx * SEND_AHEAD / 60.0

    def _threat_windows(self, r: Hop, hx: float | None, xs: tuple = ()) -> list[tuple[int, int, float]]:
        """[(w0, w1, thr)] of the bombs still to hurt that cover her (her x hx and the xs she may be at): game frames
        (k) her box bottom must stay at or above thr (u above the floor)."""
        c = self.cfg
        out = []
        for b in r.bombs.values():
            if b["end"]:
                continue
            if hx is None:
                if not b.get("cover"):
                    continue
                dx = b.get("dx", 0.0)
            else:
                dxs = [abs(x - b["x"]) for x in (hx,) + tuple(xs)]
                dx = min(dxs)
                if dx >= R + HALF_W + c.x_pad:
                    continue
                b["cover"] = True
                b["dx"] = round(dx, 3)
            if b["on"] is not None:
                w0, w1 = b["on"], b["on"] + c.dur - 1
            else:
                w0, w1 = b["a"] + c.lead_lo, b["a"] + c.lead_hi + c.dur - 1
            thr = bomb_top(b["y"], max(0.0, dx - c.x_pad)) + c.margin
            out.append((w0 - c.pre, w1 + c.post, thr))
        return out

    def _body(self, r: Hop, k: int) -> tuple[float, float, str]:
        """Its body (top, front, state) predicted at frame k (from the antic entry)."""
        c = self.cfg
        kc = (r.tc - r.ta) * 60.0 if r.tc is not None else c.cast2_k
        if k < kc - 6:
            return (*body_at("Spell Antic", k), "Spell Antic")
        if k < kc:
            return (*BODY_TALL, "Cast 1")
        if k < kc + c.cast2_len:
            return (*body_at("Cast 2", k - kc), "Cast 2")
        return (*BODY_IDLE, "Idle")

    def _body_now(self, st: str | None, tin: float) -> tuple[float, float, bool]:
        """Its body (top, front) on the frame a slash pressed for this tick's mask meets it (state frame + SEND_AHEAD
        + 1), from the STATE's Control state (the lower top where the state may turn over), and whether it will be in
        Idle then."""
        c = self.cfg
        kst = tin * 60.0 + SEND_AHEAD + 1
        if st in CAST_ST:
            top, front = body_at(st, kst)
            if st == "Cast 2" and kst >= c.cast2_len:
                return min(top, BODY_IDLE[0]), max(front, BODY_IDLE[1]), True
            return top, front, False
        if st == "Idle":
            return BODY_IDLE[0], BODY_IDLE[1], True
        return BODY_IDLE[0], BODY_IDLE[1], False

    def _slash_meets(self, gap: float, bottom: float, top: float) -> bool:
        """The side slash from her box (bottom above the floor) meets a body box gap u ahead (her box centre to its
        near edge) whose top is top: x reach and the lower edge."""
        c = self.cfg
        if gap > SLASH_X[1] - c.reach_spare:
            return False
        return bottom + HALF_H + slash_low(max(gap, 0.0)) < top - c.y_spare

    def _score(self, r: Hop, k_ready: int, gap: float, w_end: int):
        """score(H, P): the slashes that can land from k_ready to the hop's landing (the highest lane), the
        rhythm slash_cd, no slash on the Idle Clapper before w_end (the hold and the bomb windows)."""
        c = self.cfg

        def score(H: int, P: int) -> int:
            hi_t = HOP_HI[H]
            end = P + len(hi_t)
            n, t = 0, k_ready
            idle_from = max(w_end, P + H + 1)
            while t < end:
                j = t + 1 - P
                bot = 0.03 if j < 0 else (hi_t[j] if j < len(hi_t) else 0.03)
                top, _, bst = self._body(r, t + 1)
                if bst == "Idle" and t + 1 < idle_from:
                    t += 1
                    continue
                if self._slash_meets(gap, bot, top):
                    n += 1
                    t += c.slash_cd
                else:
                    t += 1
            return n
        return score

    def _step(self, r: Hop, f: int, s: dict, e: dict, st: str | None, tin: float, ground: bool, accepting: bool,
              latch) -> int | None:
        c = self.cfg
        k = r.k                                           # the frame this tick's mask lands on
        h = s.get("hero") or {}
        tm = h.get("tm") or {}
        cx = float(e["pos"][0]) + float((e.get("vel") or [0.0, 0.0])[0]) * SEND_AHEAD / 60.0
        hx = self._hx(s)
        d = (hx - cx) * r.face                            # her x in front of its centre on the mask's frame
        toward = M_R if -r.face > 0 else M_L
        away = M_L if toward == M_R else M_R
        bottom = float((h.get("box") or [0, FLOOR, 0, 0])[1]) - FLOOR
        if k > c.k_max:
            self._close("done", "timeout")
            return None
        if r.phase == "over":
            return self._over_step(r, f, s, e, ground)
        # the hop committed: hold, air slashes, steer, land
        if r.phase == "hop":
            j = k - r.P
            if ground and j > 4:
                r.k_land = k
                if not (self.b2 and self._b2_left(r, hx, cx)):
                    self._close("done", "landed")
                    return None
                # (SP13b BOMBS2) covering bombs left (the other row / the second hop): back to the stance
                r.phase, r.P, r.H, r.plan = "stance", None, None, None
                r.rehop += 1
            else:
                if j > c.land_wait:
                    self._close("done", "no landing")
                    return None
                if self.b2 and self.cfg.air2 and j >= r.H:
                    # (SP13b BOMBS2) a covering window the hop's lowest lane does not clear and no second hop can (it
                    # starts before the landing + rise2): from the hold's end the umbrella / drift plan of the hero
                    # model holds her over it (the latest safe umbrella press)
                    lo_t = HOP_LO[r.H]
                    land_k = r.P + len(lo_t)
                    bad = [w for w in self._threat_windows(r, hx) + self._fc_windows(r, hx)
                           if w[1] >= k and w[0] < land_k + self.cfg.rise2 and any(
                               (lo_t[jj - r.P] if 0 <= jj - r.P < len(lo_t) else 0.0) < w[2]
                               for jj in range(max(w[0], k), w[1] + 1))]
                    if bad:
                        m = self._air_plan(r, f, s)
                        if m is not None:
                            return m
                m = M_J if j < r.H else 0
                m |= self._air_keys(r, s, e, st, tin, k, d, cx, hx, toward, away, tm, j)
                return m
        # stance: the cast over and nothing covers her -> the planner
        cast = st in CAST_ST
        xs = self._stand_xs(r, cx)
        thr = self._threat_windows(r, hx, xs)
        free = False
        if self.b2:
            # (SP13b BOMBS2) every caster's bombs at her x / the stance: the forecast's windows join the seen ones
            fcw = self._fc_windows(r, hx, () if (not cast and st not in ("Idle", None)) else xs)
            thr = thr + fcw
            if not cast and st not in ("Idle", None) and thr:
                # its next move began with covering bombs left: free mode (no stance, no slash on it), the keys only
                # while a window starts within look2 frames
                free = True
                r.free += 1
                if min(w0 for w0, _, _ in thr) - k > c.look2:
                    return None
        if not cast and not thr:
            self._close("done", "over")
            return None
        if not cast and st not in ("Idle", None) and not free:
            self._close("done", "next")                   # its next move began (no hop was due)
            return None
        # the hop: plan on every tick once a covering bomb is seen
        prev = r.sent[-1][1] if r.sent else 0
        cont = M_A | toward if (r.presses and k - r.presses[-1][0] == 1 and prev & M_A) else 0
        if r.pm is not None:
            # (SP13b TWO_PMCAST) the over plan instead of the hop: its jump press when due, else the stance below
            m = self._pm_step(r, f, s, e, ground)
            if m is not None:
                return m
        if thr and r.pm is None:
            if not ground:
                if min(w0 for w0, _, _ in thr) - k < 12:
                    # a covering bomb lights soon and she is in the air (a start in the air, a knock-back): the hop
                    # cannot be pressed - the planner (its bomb forecast) decides; (SP13b BOMBS2) unless the hero
                    # model has a fall / umbrella / drift plan clear of every bomb
                    if self.b2 and c.air2:
                        m = self._air_plan(r, f, s)
                        if m is not None:
                            return m
                    self._close("abort", "air")
                    return None
                if free:
                    return 0
            else:
                last = r.presses[-1][0] if r.presses else -99
                cd = float(tm.get("atk_cd") or 0.0)
                k_ready = max(k, last + c.slash_cd, k + int(math.ceil(max(0.0, cd * 60.0 - (SEND_AHEAD - 1)))))
                key = [(int(a), int(b), round(x, 2)) for a, b, x in thr]
                plan = r.plan
                if (self.b2 and plan is not None and plan["P"] >= k and plan["thr"] != key
                        and self._plan_holds(plan, thr, k)):
                    # (SP13b fp1) the forecast's windows move a frame or two every tick: a plan that still clears them
                    # all is kept (re-planning each tick slid the press to the middle of a shrinking range until none
                    # was left - 3 of fp1's 10 small-rune hits, the hop never pressed)
                    plan = r.plan = {**plan, "thr": key}
                if plan is None or plan["thr"] != key or plan["P"] < k:
                    # (re)plan when the covering bombs change (a new one, a light seen) or the press was missed; a
                    # plan is kept otherwise (its slack shrinks as the frames pass)
                    body_front = self._body(r, k)[1]
                    gap = max(0.0, d - body_front)
                    w_end = max(w1 for _, w1, _ in thr)
                    sc = self._score(r, k_ready, min(gap, SLASH_X[1] - 0.5), w_end)
                    if self.b2:
                        # (windows already on cannot be cleared by a press now: the rest is planned)
                        plan = hop_plan2([w for w in thr if w[0] > k], k, range(c.h_min, c.h_max2 + 1), c.min_slack,
                                         score=sc, rise=c.rise2)
                    else:
                        plan = hop_plan(thr, k, range(c.h_min, c.h_max + 1), c.min_slack, score=sc)
                    if plan is not None:
                        r.plans += 1
                        plan = r.plan = {**plan, "k": k, "thr": key}
                if plan is None:
                    r.late += 1
                else:
                    if plan["P"] <= k:
                        ok = latch is None or bool(int(latch(M_J)) & M_J)
                        if ok:
                            r.P, r.H = k, (self._lowest_hold(plan, thr, k, c.h_min) if self.b2 else plan["H"])
                            r.phase = "hop"
                            if self.b2:
                                r.big += r.H > 16
                                r.split += plan.get("n", 0) < plan.get("of", 0)
                            m = M_J | cont
                            if not cont and self._slash_ok(r, s, e, st, tin, k, d, tm, air=False, j=0):
                                r.presses.append((k, False, round(d, 2), 0.0))
                                m |= M_A | toward
                            return m
        # the ground stance: a slash when it meets its body, else walk into the band
        if cont:
            return cont                                   # the slash's second frame
        if free:
            return 0                                      # (BOMBS2) its caster moves on: stand for the bombs
        if self._slash_ok(r, s, e, st, tin, k, d, tm, air=not ground, j=None):
            r.presses.append((k, not ground, round(d, 2), round(bottom, 2)))
            return M_A | toward
        lo, hi = c.stand_lo, c.stand_hi
        x0d = None if r.x0 is None else (hx - r.x0) * r.face
        clip = str((h.get("anim") or {}).get("clip") or "")
        if "Sprint" in clip or "Dash" in clip:
            return 0                                      # a held key would keep the sprint going (into its body)
        if d > hi + 0.5 * WALK_U or (x0d is not None and x0d > c.x0_hi):
            return toward
        if d < lo - 0.5 * WALK_U or (x0d is not None and x0d < c.x0_lo):
            return away
        return 0

    # ---- SP13b SSBOT_FORUM_TWO_PMCAST ----

    def _over_planner(self, r: Hop, f: int, s: dict, e: dict, ground: bool):
        """push_cast.OverPlanner for this tick (the policy's hero model) and the contact's target mask frame."""
        from ssbot.combat import push_cast as _pc
        from ssbot.combat import rune_pogo as _rpg
        pc = self.pccfg
        h = s.get("hero") or {}
        F0 = f + SEND_AHEAD
        bb = _rpg.body_box(e)
        fx = float(e["pos"][0])
        b_box = (bb[0], _pc.FLOOR, bb[2], _pc.FLOOR + _pc.TALL_TOP)
        oth = [x for x in _sp.clappers(s) if x.get("iid") != r.iid]
        f_box = _rpg.body_box(oth[0]) if oth else None
        cd = (h.get("tm") or {}).get("atk_cd")
        rdy = F0 + (0 if cd is None else max(0, int(math.ceil(float(cd) * 60.0 - (SEND_AHEAD - 1)))))
        j_held = bool(int((s.get("act") or {}).get("mask") or 0) & M_J)
        fc = h.get("facing")
        kc = (r.tc - r.ta) * 60.0 if r.tc is not None else self.cfg.cast2_k
        low_F = F0 + int(round(kc + 14 - r.k))
        tgt = F0 + int(round(kc + pc.tgt_c - r.k))
        x0 = r.x0 if r.x0 is not None else fx
        clip = str((h.get("anim") or {}).get("clip") or "")
        ctx = _rpg.Ctx(F0=F0, b_box=b_box, b_x=fx, b_ok=True, tx=x0 + r.pm * 0.5 * (pc.land_lo + pc.land_hi),
                       face=1 if fc is None or float(fc) >= 0 else -1, ground=ground, atk_ready_f=rdy,
                       j_held=j_held, f_box=f_box, bombs=self._bk, bomb_m=pc.bomb_m,
                       gliding=clip.startswith("Umbrella") and "Deflate" not in clip)
        return _pc.OverPlanner(self._sim, ctx, pc, low_F, x0, r.pm), tgt

    def _pm_end(self, r: Hop, why: str) -> None:
        r.pm, r.pm_why = None, why
        self.pm_giveup = why

    def _pm_step(self, r: Hop, f: int, s: dict, e: dict, ground: bool) -> int | None:
        """The cast route in the stance: the over plan searched every `every` ticks from k_plan0 (kept and checked
        between), its jump pressed when due (-> phase over); none by k_last (or no hero model): the low hop as before."""
        import time
        from ssbot.combat import rune_pogo as _rpg
        pc = self.pccfg
        k = r.k
        if self._sim is None or k > pc.k_last:
            self._pm_end(r, "no plan" if self._sim is not None else "no sim")
            return None
        if not ground or k < pc.k_plan0:
            return None
        F0 = f + SEND_AHEAD
        pl, tgt = self._over_planner(r, f, s, e, ground)
        if not (r.op is not None and r.op.jump[0] >= F0 and (r.ticks % pc.every) and pl.again(r.op)):
            t0 = time.perf_counter()
            r.op = pl.best_over(target_F=tgt)
            r.op_plans += 1
            r.op_ms += (time.perf_counter() - t0) * 1e3
        if r.op is not None and r.op.jump[0] <= F0:
            r.phase, r.op_k, r.op_j0 = "over", k, r.op.jump[0]
            return _rpg.mask_at(r.op, F0)
        return None

    def _over_step(self, r: Hop, f: int, s: dict, e: dict, ground: bool) -> int | None:
        """The committed over plan: its keys; checked every tick (failing with a danger within 8 frames: rune_pogo's
        best_air toward the landing band); landed after the contact -> done (TwoPlay's herd); landed before -> done."""
        from ssbot.combat import rune_pogo as _rpg
        p = r.op
        F0 = f + SEND_AHEAD
        if ground and F0 > r.op_j0 + 6:
            ok = p.contact is not None and F0 > p.contact
            r.pm_why = "over" if ok else "early land"
            if not ok:
                self.pm_giveup = r.pm_why
            self._close("done", "pm landed" if ok else "pm early land")
            return None
        h = s.get("hero") or {}
        clip = str((h.get("anim") or {}).get("clip") or "")
        vy = float((h.get("vel") or [0.0, 0.0])[1])
        if p.press is not None and F0 > p.press and r.op_bounce is None and (
                clip.startswith("DownSpikeBounce") or (vy > 12.0 and F0 > p.press + 2)):
            r.op_bounce = F0
        if p.contact is not None and r.op_bounce is None and F0 > p.contact + 4 and not ground:
            # (fp1) the down slash missed F's head (no bounce): the plan is void - the planner decides
            r.pm_why = "miss"
            self.pm_giveup = "miss"
            self._close("abort", "pm miss")
            return None
        if r.op_bounce is not None and not ground and e is not None and vy < 0:
            # (SP13b fp2) the landing guard: falling onto F's body (it turned to face her, her slashes pushed it toward
            # her landing, the real drift fell short) -> the key away from its centre, to its wall side
            from ssbot.combat import rune_pogo as _rpg
            bx0, _by0, bx1, _by1 = _rpg.body_box(e)
            g = self.pccfg.guard_u
            hx = _sp.hero_x(s)
            if bx0 - g - HALF_W < hx < bx1 + g + HALF_W:
                fx = float(e["pos"][0])
                side = 1 if hx >= fx else -1
                r.op_guard += 1
                m = _rpg.mask_at(p, F0) & ~(M_L | M_R)
                return m | (M_R if side > 0 else M_L)
        if self._sim is not None and e is not None and (p.press is None or F0 <= p.press):
            pl, _tgt = self._over_planner(r, f, s, e, ground)
            if not pl.again(p):
                r.op_fail += 1
                if p.bad is not None and p.bad - F0 < 8 and not ground:
                    alt = pl.best_air(_sp.hero_x(s))
                    if alt is not None and alt.bad is None:
                        alt.contact = alt.contact if alt.contact is not None else p.contact
                        r.op = p = alt
                        r.op_alt += 1
        return _rpg.mask_at(p, F0)

    # ---- SP13b SSBOT_FORUM_TWO_BOMBS2 ----

    def _fc_windows(self, r: Hop, hx: float, xs: tuple = ()) -> list[tuple[int, int, float]]:
        """The forecast's bombs (every caster: self._bk, frames from the STATE) that cover her x hx or the xs she may be
        at: [(w0, w1, thr)] in the run's frames, still to end; kept on the run for critical()."""
        c = self.cfg
        bk = self._bk
        out = []
        if bk is not None and len(bk):
            k0 = r.k - SEND_AHEAD
            for o, bx, by, _r, on, off in bk:
                if k0 + off < r.k:
                    continue
                dx = min(abs(x - bx) for x in (hx,) + tuple(xs))
                if dx >= R + HALF_W + c.x_pad:
                    continue
                thr = bomb_top(by, max(0.0, dx - c.x_pad)) + c.margin
                out.append((int(k0 + on) - c.pre, int(k0 + off) + c.post, round(thr, 2)))
                r.owners.add(int(o))
        r.fcw = out
        return out

    @staticmethod
    def _lowest_hold(plan: dict, thr: list, k: int, h_min: int) -> int:
        """Task 182 seq 289 (the person: the low hop, slashing through it): a plan made early holds high for the windows the
        forecast showed then (the rows still to come, 4 windows, H 20-26), and is kept while it still clears them; at the
        press, this tick's windows decide: the lowest hold whose lowest lane clears every window of this hop (those starting
        after the press, up to the plan's own w_end; a split plan's later ones are its second hop's) from the press frame k,
        none landing before its last window; else the planned hold."""
        rel = [w for w in thr if k < w[0] <= plan.get("w_end", 1 << 30)]
        for H in range(h_min, plan["H"]):
            lo_t = HOP_LO[H]
            if all(w1 - k < len(lo_t) and all(lo_t[j] >= th for j in range(w0 - k, w1 - k + 1)) for w0, w1, th in rel):
                return H
        return plan["H"]

    @staticmethod
    def _plan_holds(plan: dict, thr: list, k: int) -> bool:
        """The planned hop (press P, hold H: the lowest lane) still clears every window still to end (those it was
        not planned for and cannot clear: a split plan's later windows are the second hop's)."""
        lo_t = HOP_LO[plan["H"]]
        P = plan["P"]
        land = min(P + len(lo_t), plan.get("w_end", 1 << 30) + 1)
        for w0, w1, th in thr:
            if w1 < k or w0 >= land:
                continue
            for j in range(max(w0, k) - P, w1 - P + 1):
                if j < 0 or j >= len(lo_t) or lo_t[j] < th:
                    return False
        return True

    def _b2_left(self, r: Hop, hx: float, cx: float) -> bool:
        """Covering windows still to come at her x (the seen bombs and the forecast)."""
        thr = self._threat_windows(r, hx) + self._fc_windows(r, hx)
        return any(w1 >= r.k + 1 for _, w1, _ in thr)

    def _air_plan(self, r: Hop, f: int, s: dict) -> int | None:
        """In the air with a covering bomb soon: the hero model's plans (fall / the umbrella pressed at u and held /
        a drift key) against every lit bomb of the forecast (grown by air_m) and the Clappers' bodies (outside the
        i-frames); the first safe one in the order fall without a key, fall with the shortest drift, the umbrella
        (latest press first); its keys for this mask frame, None when none is safe."""
        sim, bk = self._sim, self._bk
        if sim is None or bk is None:
            return None
        import numpy as np
        from ssbot.combat import rune_pogo as _rpg
        from ssbot.knowledge import kinematics as kin
        c = self.cfg
        h = s.get("hero") or {}
        F0 = f + SEND_AHEAD
        clip = str((h.get("anim") or {}).get("clip") or "")
        gliding = clip.startswith("Umbrella") and "Deflate" not in clip
        j_held = bool(int((s.get("act") or {}).get("mask") or 0) & M_J)
        plans = []
        for dk, ds in ((0, (0,)), (M_L, (6, 14, 30)), (M_R, (6, 14, 30))):
            for d in ds:
                plans.append(_rpg.Plan("fall", dk, F0, F0 + d, why=f"fall{d}"))
                if gliding:
                    plans.append(_rpg.Plan("umb", dk, F0, F0 + d, hold_j=True, why=f"hold{d}"))
                else:
                    u0 = 2 if j_held else 0
                    for u in (u0 + 10, u0 + 6, u0 + 3, u0):
                        plans.append(_rpg.Plan("umb", dk, F0, F0 + d, umb=F0 + u, why=f"umb{u}d{d}"))
        cm = np.stack([_rpg.plan_cmds(p, F0, c.air_h) for p in plans])
        ro = sim.roll(cm)
        off = sim.off
        bad = _rpg.bomb_hits(ro, np.asarray(bk, float), off - SEND_AHEAD, c.air_m)
        inv = (ro.flags & kin.F_INVULN) != 0
        for e in _sp.clappers(s):
            bad |= _rpg.box_hits(ro, _rpg.body_box(e), 0.1) & ~inv
        bad[:, :off + 1] = False
        ok = [p for n, p in enumerate(plans) if not bad[n].any()]
        if not ok:
            return None
        p = ok[0]
        r.air.append((r.k, p.why))
        return _rpg.mask_at(p, F0)

    def _stand_xs(self, r: Hop, cx: float) -> tuple:
        """The x she may stand at before the bombs light (the band's ends), for the cover check."""
        c = self.cfg
        a = cx + r.face * c.stand_lo
        b = cx + r.face * c.stand_hi
        if r.x0 is not None:
            a = r.x0 + r.face * max(c.x0_lo, min(c.x0_hi, c.stand_lo + (cx - r.x0) * r.face))
            b = r.x0 + r.face * max(c.x0_lo, min(c.x0_hi, c.stand_hi + (cx - r.x0) * r.face))
        return (a, b)

    def _slash_ok(self, r: Hop, s: dict, e: dict, st: str | None, tin: float, k: int, d: float, tm: dict,
                  air: bool, j: int | None) -> bool:
        """A side slash pressed on frame k (the mask's) meets its body on k + 1: our rhythm, the attack ready, the x
        reach and the lower edge (her bottom on k + 1: the hop's highest lane when j is given, else now + her vy)."""
        c = self.cfg
        if r.presses and k - r.presses[-1][0] < c.slash_cd:
            return False
        cd = tm.get("atk_cd")
        if cd is not None and float(cd) * 60.0 - (SEND_AHEAD - 1) > 0.05:
            return False
        h = s.get("hero") or {}
        clip = str((h.get("anim") or {}).get("clip") or "")
        if any(x in clip for x in ("Dash", "Sprint", "Skid")):
            return False
        top, front, idle = self._body_now(st, tin)
        if idle and r.phase == "hop" and self.critical():
            return False                                  # a hit starts its next move: not inside the hop's window
        span = None
        for col in e.get("colliders") or ():
            if col.get("name") == CLAPPER and col.get("enabled") and col.get("verts_world"):
                xs = col["verts_world"][0::2]
                span = (float(min(xs)), float(max(xs)))
                break
        cx = float(e["pos"][0])
        if span is None:
            span = (cx - front, cx + front) if r.face < 0 else (cx - front, cx + front)
        near = span[1] if r.face > 0 else span[0]        # its front edge (she is in front)
        hx = _sp.hero_x(s)
        gap = (hx - near) * r.face
        if gap < -0.3:
            return False
        if j is not None and r.H is not None:
            jj = j + 1
            bot = HOP_HI[r.H][jj] if 0 <= jj < len(HOP_HI[r.H]) else 0.03
        else:
            b0 = float((h.get("box") or [0, FLOOR, 0, 0])[1]) - FLOOR
            vy = float((h.get("vel") or [0.0, 0.0])[1])
            bot = max(0.0, b0 + vy * (SEND_AHEAD + 1) / 60.0) if air else b0
        return self._slash_meets(gap, bot, top)

    def _air_keys(self, r: Hop, s: dict, e: dict, st: str | None, tin: float, k: int, d: float, cx: float, hx: float,
                  toward: int, away: int, tm: dict, j: int) -> int:
        """In the hop: the slash on the rhythm where it meets its body (its second frame), else the key toward it
        only when the gap to its body is beyond gap_hi (and never past x0_lo .. x0_hi while a bomb covers her)."""
        c = self.cfg
        prev = r.sent[-1][1] if r.sent else 0
        if r.presses and k - r.presses[-1][0] == 1 and prev & M_A:
            return M_A | toward
        if self._slash_ok(r, s, e, st, tin, k, d, tm, air=True, j=j):
            r.presses.append((k, True, round(d, 2), round(HOP_HI[r.H][min(j + 1, len(HOP_HI[r.H]) - 1)], 2)))
            return M_A | toward
        front = self._body(r, k)[1]
        gap = d - front
        covered = any(w1 >= k for _, w1, _ in self._threat_windows(r, None))
        x0d = None if r.x0 is None else (hx - r.x0) * r.face
        if gap > c.gap_hi and not (covered and x0d is not None and x0d - WALK_U < c.x0_lo):
            return toward
        if gap < c.gap_lo and not (covered and x0d is not None and x0d + WALK_U > c.x0_hi):
            return away
        return 0
