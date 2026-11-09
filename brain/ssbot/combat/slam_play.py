"""The person's slam strike as a fixed playbook (task 1v1 SP1, the person's decision 2026-10-16; forum.md 65).

SSBOT_FORUM_SLAM_PLAY=1 (default since 2026-10-16: on whenever SSBOT_FORUM_V2=1, off without v2; =0 turns it off and
every decision is the one before): when the Clapper (Song
Heavy Sentry) enters Slam Antic and the entry conditions hold, the bot plays the person's strike as a script, frame by
frame from the antic entry; otherwise (and whenever the script aborts) the rn planner decides as today.

The script (frame k counted from the antic entry, k = 0 the first STATE whose Control state reads Slam Antic minus
its state time; every k is the frame the key takes effect in the game, the STATE's act.mask; since SP2 the frames are
game frames: the game clock stands still through hit-stop freezes, SSBOT_FORUM_SLAM_PLAY_CLOCK):
  walk      k < K_JUMP: on the ground, in front of the Clapper (the side it faces), walk toward / away until the hero's
            centre is inside STAND (centre to centre, u) and stop dead; no key once inside (the person: no key on most
            frames, else toward)
  jump      K_JUMP .. K_JUMP + HOLD - 1: the jump held, no direction key (straight up)
  wait      no key
  down      K_DOWN .. K_PRESS - 1: down held (the person: 5 frames before the attack, p10/90 3.5 / 6.6)
  press     K_PRESS: down + attack; down 2 more frames
  after     never the jump (in the air it opens the umbrella); no key while the bounce rises; then the person's way
            out (over = 1): from Slam 0 + OVER_S0 the direction over its body to behind it (the other way when the wall
            behind it leaves less than OVER_ROOM from its centre, none when neither side has it), the dash at Slam 0 +
            DASH_S0 (2 frames), the key held until she lands; the planner takes over on the ground. No bounce by the
            press + 14: abort (the planner). SP5 (SSBOT_FORUM_SLAM_PLAY_SIDE / _NEAR): the side by the person's rule
            (between it and the nearer wall; two Clappers: between them) and the closer landing (no dash, near_u from
            its centre) with a side slash before it.
Slam 0 seen before the press was sent (a short antic or a late tick): the press at once while its frame is within
Slam 0 + press_late_max, else abort.
Entry conditions (checked on every tick until the script starts, at the latest at antic frame K_START_MAX): the hero
on the ground, accepting input, in front of the Clapper, the walk into STAND done by K_JUMP - 1 inside the arena. In
the air at the antic (air = 1, seen by K_AIR_MAX): the script steers toward STAND (no jump, no attack) and starts on
landing if the walk still fits; no landing by K_JUMP - 4: abort. Not accepting input (the sprint's skid, a recoil):
no start.
Abort (the planner decides again): conditions lost before the jump (not on the ground at the jump, outside BAND at the
jump), the hero hurt, the Clapper gone or out of the slam, a Slam 0 the press cannot meet.

The numbers (forum.md 65.1): the person's 29 landed strikes of the 2026-10-15 demo (0.5x; game frames): x at the antic
entry 4.3 / 6.3 / 7.5 u (p10 / 50 / 90), walk toward 0 / 10 / 22 frames, jump at 23.7 / 26.5 / 31.1 held 13.3 / 15.5 /
17.6, down 5 frames before the attack, press at 44.3 / 47.5 / 50.1 (Slam 0 -4.2 / -1.0 / +1.6) at x 4.3 / 5.0 / 5.7,
contact at Slam 0 +2.5 / +4.0 / +5.5, no jump after the press (0 of 33); the 3 hammer hits pressed at Slam 0 +2..+6.5;
after the bounce a dash in 20 of 29 (antic +69.5 / 72.5 / 75.5, about Slam 0 + 24), the key toward it from about Slam
0 + 20, landing behind it 20 of 29.
T1's live trials at 1x (forum.md 46; jump held 16, dx 4.0-6.25 u at the press): pressed at 42-51 104 of 105 safe,
at 52 0 of 12; held 11 or 16, pressed at 44-51: dx 3.75-6.25 191 of 195, dx >= 6.75 3 of 20.

    sp = SlamPlay()                                        # per episode: sp.reset()
    m = sp.step(f, s, ground)                              # the mask for frame f + 2, or None (the planner decides)
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from ssbot.combat import air_chain as _ac
from ssbot.combat import claw_strike as _cs
from ssbot.combat import jump_behind as _jb
from ssbot.combat import rune_life as _rl
from ssbot.knowledge import kinematics as kin

CLAPPER = "Song Heavy Sentry"
SLAM_STATES = ("Slam Antic", "Slam 0", "Slam 1", "Slam Effects?", "Slam 2", "Slam Recover")
M_L, M_R, M_D, M_J, M_A, M_DASH = kin.B_LEFT, kin.B_RIGHT, kin.B_DOWN, kin.B_JUMP, kin.B_ATTACK, kin.B_DASH
WALK_U = 8.25 / 60          # the hero's walk per frame (she stops dead)
SEND_AHEAD = 2              # the policy sends each ACTION for STATE frame + 2
WALL_L, WALL_R = 14.01, 48.99   # ssbot.core.forum (the import firewall keeps combat light)


def _on(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip() == "1"


def _num(name: str, default: float) -> float:
    v = os.environ.get(name, "").strip()
    return float(v) if v else default


# The person, 2026-10-16: the fast arm is the default ("the one that runs away and kills slowly would surely die
# against two Clappers"). Unset, SSBOT_FORUM_SLAM_PLAY follows SSBOT_FORUM_V2 (on with v2, off without it, like the
# small-rune switches); 0 turns it off (arm rn0 = the old rn).
ENABLED = _on("SSBOT_FORUM_SLAM_PLAY", "1" if _on("SSBOT_FORUM_V2") else "0")
# SSBOT_FORUM_SLAM_PLAY_STANCE=<u> (default 0 = off; arm rnplay6: 6): the L2 stance while the Clapper idles / walks /
# evades: on the ground <u> in front of it, centre to centre (the person's band at the antic entry, 6.2 u; it picks the
# slam 74 % of the time at 5.4-8 u). Read by combat.tactics.gauntlet; measured separately from the strike.
STANCE_U = _num("SSBOT_FORUM_SLAM_PLAY_STANCE", 0.0)
# SSBOT_FORUM_SLAM_PLAY_CLOCK (default 1; SP2, forum.md 66): the script's frames k on the game clock (Stamp.t_game_s:
# still through hit-stop freezes); 0: the STATE frame count of SP1 (a 12-frame freeze in the antic moved the press to
# Slam 0 - 15 live: no bounce, the hammer's body hit at Slam 1).
GAME_CLOCK = _on("SSBOT_FORUM_SLAM_PLAY_CLOCK", "1")
# SSBOT_FORUM_JUMP_BEHIND (task 1v1 SP3, combat.jump_behind): after a jump the hero may stand between the Clapper and a
# wall; when the stand point does not fit inside the arena, the nearest that does if it is NEAR_STAND_U or more in front
# (SP1 it3, the stand pinned: the jump at 3.6-7.25 u all succeeded), the band at the jump from NEAR_BAND_LO
NEAR_STAND_U = 3.7
NEAR_BAND_LO = 3.6
# SSBOT_FORUM_SLAM_PLAY_LATE (task 1v1 SP4, default: follows v2; forum.md 68): the declined slams of SP2 / SP3 (319 slams re-run
# through the playbook on the recordings: 16 "no input", 16 "no landing", 4 not on the ground at the jump, ...) - (a) no
# input at the antic (the sprint's Sprint Turn / Skid End after a planner dash + run, 6 of them ended at 4.8-5.5 u at
# antic frame 13-28; the umbrella, 10, landed 6-9 u out at 13-26): wait, start when input returns (a late start like
# the airborne entry); (b) an airborne entry landing at antic frame 28 (7 cases at 4.9-5.6 u, all aborted one frame
# early): the jump up to K_JUMP_LATE2 (the press at K_PRESS_MAX = 19 frames after a jump at 30); (c) a late start
# outside the jump band walks into it up to K_JUMP_LATE2. 0: SP1-SP3's playbook.
# SP4 A/B (forum.md 68.5; the person's rule "the faster arm is the default"): the SP4 switches below follow
# SSBOT_FORUM_V2 when unset (on with v2, off without it); =0 turns each off (arm rnsp40 = the SP3 default rnjb).
_V2 = "1" if _on("SSBOT_FORUM_V2") else "0"
LATE = _on("SSBOT_FORUM_SLAM_PLAY_LATE", _V2)
# SSBOT_FORUM_SLAM_AFTER (task 1v1 SP4, default: follows v2; read by combat.tactics.gauntlet): a slam the playbook does not take,
# the hero in front: never the 13 u flight past the hammer; in Slam 2 (the lunge over: Slam Collider 2 reaches 7.76 u
# in front of the Clapper at the standing hero's height, 407 live slams) OUTSIDE_U in front of it, in the recovery (the
# hammer off; its body's front edge 3.49 u to antic frame 67, then 2.25 u) AFTER_U in front with ground hits counting
# (the after-the-hammer strike, presses about antic frame 63-76)
AFTER = _on("SSBOT_FORUM_SLAM_AFTER", _V2)
# SSBOT_FORUM_SLAM_PLAY_NODASH (task 1v1 SP4, default: follows v2; the lead's "no dash + run when a slam can start"; read by
# combat.tactics.gauntlet and combat.forum_planner): while the Clapper idles / walks / evades (a slam can start any
# frame) and the hero is within NODASH_U of it, the planner's safe rows with a dash key in their first NODASH_F frames
# rank after the safe rows without one, above the landed hits (GoalPrefs.no_dash). A dash + run leaves no input for
# 10-30 frames (Dash To Run, Sprint Turn / Skid End, Sprint Air): SP2 / SP3's "no input" declines (6 skids of 16) and
# SP4 t1's sprint skid into its idle body (2 HP).
NODASH = _on("SSBOT_FORUM_SLAM_PLAY_NODASH", _V2)
NODASH_U = 10.0             # centre to centre: the playbook's reach (2.7-9 u) + a step
NODASH_F = 20               # a dash (6 frames) + the sprint's start
# SSBOT_FORUM_SLAM_PLAY_NOPOGO (task 1v1 SP4, default: follows v2; read by gauntlet / forum_planner): while the Clapper idles /
# walks / evades, the planner's safe rows whose first predicted hit on it lands from the air (a pogo, a jump slash) rank
# after the rest, above the landed hits (GoalPrefs.no_pogo). A hit sends the idle Clapper into its attack choice at
# once with the hero in the air: SP3's A/B, 10 of rnjb's 54 slams began within 12 frames of her air hit; SP4 t2, a
# pogo off its head after a rune hop bounced her to 9 u above the floor at the antic, no landing by frame 30, the
# umbrella, the hammer (2 of 2 HP hits).
NOPOGO = _on("SSBOT_FORUM_SLAM_PLAY_NOPOGO", _V2)
OUTSIDE_U = 8.3             # 7.76 + the hero's half width 0.23 + 0.3
AFTER_U = 4.3               # 3.49 + 0.23 + 0.58: in the side slash's reach of its front edge
# SP5 A/B (forum.md 69.4; f63e605, rnjb vs rnsp5, 16 episodes each: HP-hitless 15 -> 16, kill p50 26.8 -> 23.0 s,
# landed / s 0.849 -> 0.936; the person's rule "the faster arm is the default"): SIDE and NEAR follow SSBOT_FORUM_V2
# when unset (on with v2, off without it); =0 turns each off (arm rnsp50 = the SP4 default).
# SSBOT_FORUM_SLAM_PLAY_SIDE (task 1v1 SP5, default: follows v2; forum.md 69): the side the way out ends on, by the person's
# rule (2026-10-16): one Clapper - between it and the nearer wall (its centre after the lunge), so it stays off the wall
# (each side slash knocks it ~0.48 u away from the hero, toward the open floor); two Clappers - between them (the side
# toward the nearest other Clapper). Keep side = stay in front, switch side = over its body, land behind. Off: behind it
# unless the wall there leaves < OVER_ROOM (SP2: 62 of 65 landings behind it, wherever it stood).
SIDE = _on("SSBOT_FORUM_SLAM_PLAY_SIDE", _V2)
# SSBOT_FORUM_SLAM_PLAY_NEAR (task 1v1 SP5, default: follows v2): the closer landing and a side slash before it (the person:
# "if the landing is a bit closer to it, one horizontal slash before landing is best"). No dash: the air key at
# NEAR_V u / frame toward the chosen side (behind: from Slam 0 + near_s0_behind, over its body; front: from Slam 0 +
# near_s0_front, away from it) until the hero's centre is near_u from the Clapper's centre on that side, one frame of the
# other key (she turns to face it), then the side slash when it can meet its body (the press >= the down press +
# slash_cd, her centre low enough: the body top 3.9 u above the floor, the slash 0.56 u below her box centre) and no
# key to the landing. Behind only when she clears its back (the turned front -2.25 u + her half width + 0.3) by Slam 0
# + near_cross_s0 (her box bottom still 4.2 u above the floor; the probes' bounce: apex Slam 0 + 23 at 6.9 u above
# the standing y, the landing at Slam 0 + 52-55) and the landing spot fits inside the arena; else the other side; else
# the old way out. Off: SP1's way out (the dash at Slam 0 + 23, landing 6.6-9.5 u behind it).
NEAR = _on("SSBOT_FORUM_SLAM_PLAY_NEAR", _V2)
# SP6 A/B (forum.md 70; d950e0a, rnjb vs rnsp6, 32 episodes each: landed / s 0.958 -> 1.008, kill p50 23.1 -> 22.0 s,
# strikes per slam 1.87 -> 2.55, HP-hitless 31 -> 30 - the two extra hits small rune bombs, none in a slam; the person,
# 2026-10-16: "the early slam antic must slash"): EARLY follows SSBOT_FORUM_V2 when unset; =0 turns it off (arm rnsp60).
# SSBOT_FORUM_SLAM_PLAY_EARLY (task 1v1 SP6, default: follows v2; forum.md 70): side slashes on the ground in the early antic,
# then the playbook's walk / jump / strike as before (the person, 2026-10-16: "try to land one more hit in the antic").
# The person's three mixed fights of the 2026-10-15 demo (`m2_play\sp6\human_early.json`): in reach at the antic entry
# (2.65-4.33 u), a hit at antic frame 0.5 (a slash pressed before it) and one at 14.5-20 (the attack cooldown 0.3 s =
# 18 frames), each knocking the Clapper 0.48 u away (it does not move otherwise in the antic), then the walk to 4.7-5.5
# u and the jump at 30-31: 2-3 hits per slam vs 1 (the 194816a1 fight, no early slash). Here: while k <= early_k_max,
# on the ground, walk into EARLY_STAND (in the side slash's reach of its body: 2.25 + 3.12 = 5.37 u centre to centre)
# and press the side slash (the key toward it on the press frame) whenever the attack is ready (our own presses
# early_cd apart and the STATE's atk_cd) and the slash from her x at the mask's frame meets its body box; after the last
# early press the walk into STAND as before (a hit leaves her ~1 u farther: its 0.48 u + her recoil ~0.5 u).
EARLY = _on("SSBOT_FORUM_SLAM_PLAY_EARLY", _V2)
# SSBOT_FORUM_TWO_PLAY (task 1v1 SP7; since SP9a follows SSBOT_FORUM_V2, =0 off; forum.md 71 / 76): two Clappers (the final wave, Forum_W_w13). Off, the
# playbook follows the first Clapper of the STATE only (clapper()): SP7's baseline (8 w13 episodes of the v2 default)
# saw 7 of its 30 slams, and 12 of the 13 hammer hits came from the other one. On: the script follows the Clapper that
# enters Slam Antic (the nearest to the hero when both do; a handled slam is not looked at again until that Clapper
# leaves it) and does not start while the other one can reach the stand point during the strike (TWO_DANGER: in a jump
# move - its landing aims 5.27 u in front of her -, in its hammer within TWO_SLAM_U of the stand point, casting the small
# runes within TWO_CAST_U, in its recovery within TWO_BODY_U, or its jump cast's rune circle - centre 6.48 u in front of
# the landing, r 7.19: -0.7 .. +13.7 u, lit 63-86 frames after the landing - still to burst over the stand point). The
# other one cannot start a move while this one is in its antic .. Slam 1 (Buddy Is Attacking), only finish one.
# SP9a A/B (forum.md 76): follows SSBOT_FORUM_V2 when unset (=0 off), with the SP9a switches
TWO_PLAY = _on("SSBOT_FORUM_TWO_PLAY", _V2)
TWO_JUMP_ST = ("Jump Antic", "Cast Slam Antic", "Cast Slam Antic 2", "Jump Aim", "Cast Jump", "Jump", "Air")
TWO_SLAM_U = 12.5           # the hammer reaches 12 u in front of its centre (+ her half width 0.23 + 0.3)
TWO_CAST_U = 9.0            # the small runes' rings around the caster
TWO_BODY_U = 4.5            # its body in Slam Recover (front 3.49 u + 0.23 + 0.3; the lunge is over)
TWO_RUNE = (-1.2, 14.2, 1.45)   # the rune circle's span from the landing along its facing (u) and its last lit second
# SSBOT_FORUM_TWO_RUNEGATE (task 1v1 SP11-0, default off; SP10a / SP10c audits: the gate above declined 22 of 189 close
# slams in SP10c's T2 by blocking from the other one's landing to + 1.45 s while its circle hurts only 6-8 frames from
# landing + 65 .. 77): the gate on the circle's lit window at the strike's frames. The circle is a dome (an octagon of r
# 7.19 centred 0.34 u above the floor, landing + 6.48 u along its facing leftward / + 6.75 rightward, bigrune
# answer.txt); the strike puts her at the stand point, her box bottom RG_H10[k // 2] u above the floor at antic frame k
# (p10 of 737 struck slams of SP10b / SP10c: on the ground to k 26, 4.1-4.4 u at the press k 44-52, the bounce's apex
# 6.9 u at k 72). On: the start is declined only when for some strike frame k inside the lit window (landing + 65 - RG_M
# .. landing + 85 + RG_M) her box at (the stand point, RG_H10) meets the dome, and never once that circle was seen lit
# and then unlit (burst). Offline on the 60 gated slams of SP10b / SP10c: 10 released (4 lost no HP under the planner, 4
# the hammer, 1 the body, 1 the rune), 50 still declined - the dome covers the bounce over the stand point. Live (SP11-0
# fixed points + the A/B arms, 3251a4a .. 9789b37): 12 starts it let through, 7 struck, 10 / 12 without HP lost to the
# antic + 120 (none by the rune; a hammer after a strike without bounce, the other one's landing after a "no landing")
# - below the 90 % gate: stays off (=1 on).
TWO_RUNEGATE = _on("SSBOT_FORUM_TWO_RUNEGATE")
RG_H10 = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.37, 0.72, 1.41, 2.11, 2.46, 3.15, 3.78,
          4.05, 4.41, 4.39, 4.31, 4.11, 3.86, 4.2, 4.66, 5.18, 5.7, 6.01, 6.32, 6.6, 6.79, 6.86, 6.9, 6.86, 6.71, 6.6,
          6.32, 5.93, 5.7, 5.18, 4.55, 4.2, 3.44, 2.57, 2.1, 1.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
RG_LIT = (65, 85)           # the circle's lit frames after the landing (first lit p5 65 / p95 77, 6-8 frames)
RG_M = 3                    # frames of margin on both ends
RG_R = 7.19                 # the dome's radius, its centre 0.34 u above the floor
RG_C = (6.48, 6.75)         # its centre in front of the landing: facing left / right
# SSBOT_FORUM_TWO_STRIKEGUARD (task 1v1 SP12a, default off; the SP11 cause audits' second cause - the slam playbook
# striking one Clapper while the other one hit her: 22 HP losses in SP11b's 128 default episodes, 11 of them the other
# one's small runes, 5 its jump's falling body in her bounce, 4 its body, 2 its jump landing): TWO_GUARD extended to
# the strike itself. The start check (and every tick of the walk until the jump: abort, the planner decides) declines
# when on the strike's path - her walk from her x to the stand point at WALK_U a frame, the stand point from the jump
# with her box bottom RG_H10 (p10 of 737 struck slams) up to SG_END_K - a small-rune bomb of the other one (rune_bombs'
# per-bomb forecast, SG_BOMB_M u) is lit ("other bomb"), the other one's body (+ SG_BODY_PAD) is ("other body"), or,
# during the walk, the other one enters a jump move or a cast within TWO_CAST_U ("other <state>": the start check has
# these already). The way out's landing side also avoids a bomb lit at its landing (_guarded_spot, SG_LAND_K). Stats
# slam_play.sg (iid, antic entry, k, why, phase).
STRIKEGUARD = _on("SSBOT_FORUM_TWO_STRIKEGUARD")
# SP12a fp1 (fc8a24e, 32 w13 episodes): the bomb part declined 15 strikes, 7 of them without HP lost to antic + 120 (the
# planner then met the hammer at + 43 .. 55 or the bombs themselves); its body / jump parts 5 of 6. =0 drops the bomb
# part (the start / walk check and the landing side); the body / jump parts stay (fp2)
SG_BOMBS = os.environ.get("SSBOT_FORUM_TWO_STRIKEGUARD_BOMB", "1").strip() != "0"
SG_END_K = 96               # the strike's path is checked to this antic frame (the bounce lands ~Slam 0 + 52)
SG_BOMB_M = 0.25            # bomb margin (u): rune_bombs.BOMB_M 0.15 + 0.1 for the walk's timing
SG_BODY_PAD = 0.55          # her half width + 0.3 around the other one's body
SG_LAND_K = (92, 112)       # the way out's landing window (antic frames)
# SSBOT_FORUM_TWO_SIDE (SP7, default off): the way out's side with two Clappers. SP5's rule lands between them; in SP7's
# first trial (t1, e450b7a) 3 of 20 struck slams lost HP to the other one's hammer 115-128 frames after the antic: it
# was idle 9.7-13.8 u away, started its slam the moment the struck one's Slam 1 ended (Buddy Is Attacking releases
# it) and hammered ~10 frames after her landing (three more such hits came on the next slam, not struck, she still in
# the bounce). On: when the other one is free (TWO_FREE_ST) and within TWO_FOLLOW_U of the landing between them (its
# hammer 12.5 u + the lunge 3.6 u), land on the far side of the struck one (behind it, NEAR's clearance and room rules
# still apply; else in front as before).
TWO_SIDE = _on("SSBOT_FORUM_TWO_SIDE")
TWO_FREE_ST = ("Idle", "Walk", "Evade Scuttle", "Slam Antic", None)   # free, or its slam already begun
TWO_REACH_U = 13.0          # the other one's follow-up hammer from its centre now (12 u with the lunge; slam_out_u 13: 0
#                             hits in 1v1). t2 (ab30fbf, NEAR's 3.7 u on the far side): 24 of 25 struck slams safe, but
#                             13 of 17 slams not struck lost HP, most of them started while she was still in the bounce
#                             7.4-8.3 u from the slammer: with the other one closer than 3.7 + 13 u the far side's 3.7 u
#                             is in its reach too -> "two-far": SP1's dash way out on that side (lands 6.6-9.5 u out)
# SSBOT_FORUM_TWO_HANDOFF (task 1v1 SP10b; follows v2 since the SP10b A/B, below; twoslam answer.txt R2): the second hammer. With TWO_PLAY the run
# stays on the struck Clapper A until her landing; the other one's (B's) slam began in the meantime, and its run
# opened at antic frame 15-40 was cut at once by K_START_MAX 14 ("late": 125 of the 186 failed second strikes; B struck
# 0 / 145 with the run still on A at B's antic + 10, 95 / 136 once it was free; the failures lost HP 148 / 186). On:
# when a run that pressed closes (the landing, A gone, k_end), the run on B opened within HO_GAP_F frames (at once on
# the landing tick) is a LATE start (Run.late: the jump up to K_JUMP_LATE2 30, the late walk into BAND, the press 18
# frames after the jump, at K_PRESS_MAX_LATE 48 at the latest) when its antic frame is <= K_JUMP_LATE2.
# SP10b A/B (e4d6365, 32 episodes per arm, the same seeds: landed / s 1.241 -> 1.387, both Clappers killed 13 -> 18 / 32,
# HP-loss hits / min 5.42 -> 3.74, B struck in k_land 8-29 0 / 9 -> 12 / 13; the person's rule "more landed per s and
# kills, not more HP hits per min"): TWO_HANDOFF and SLAM_REACH_NAME follow SSBOT_FORUM_V2 when unset (on with v2, off
# without it); =0 turns each off (arm rnsp10b0 = the SP10a default).
TWO_HANDOFF = _on("SSBOT_FORUM_TWO_HANDOFF", _V2)
HO_GAP_F = 4
CS_KEEP_F = 4               # SP13 SSBOT_FORUM_CLAWSTRIKE: a lost plan this close to its Clawline press is kept
# ... and its landing (fixed-point t1, f3d6d62: B struck 7 / 11 hand-offs of k_land 8-29; the four failures landed 7.8-8.3 u
# in front of B - A to B 11.5-11.9 u - and could not walk into BAND by K_JUMP_LATE2): while B is in Slam Antic before
# her turn key, SP5 NEAR's landing between them aims at B's stand (HO_STAND_U in front of B's centre) when that is
# farther from A than near_u_front (no side slash on A from there)
HO_STAND_U = 5.1
# SSBOT_FORUM_TWO_TIGHT (task 1v1 SP10b, default off; twoslam answer.txt R3): B enters Slam Antic before A's Slam 0 +
# TIGHT_S0 (the bounce's apex): B's Slam 0 comes <= 18 frames after her landing and no strike reaches it (0 / 55 struck,
# 53 / 55 lost HP; at the landing she is 3.8-6.1 u in front of B, inside its hammer). On: no pre-landing side slash,
# SP1's way out over A to its far side (the dash at Slam 0 + 23; lands 6.6-9.5 u behind A's centre) when the room
# behind A is >= OVER_ROOM and that landing is >= TWO_REACH_U from B; after the landing no key (the planner's jump
# toward B held off) until B's Slam 2, B leaves its slam, she is hurt, or TIGHT_HOLD_S.
TWO_TIGHT = _on("SSBOT_FORUM_TWO_TIGHT")
TIGHT_S0 = 23               # game frames after A's Slam 0
TIGHT_LAND_U = 6.6          # SP1's way out: the landing behind its centre (6.6-9.5 u)
TIGHT_HOLD_S = 1.2
TIGHT_DASH_ROOM = 10.5      # the dash way out needs this room behind A's centre (t1, f3d6d62: two dashes with 7.3 / 7.6 u
#                             of room flew into the wall - a wall slide, no landing, the planner's wall jump back)
# SSBOT_FORUM_SLAM_REACH_NAME (task 1v1 SP10b; follows v2 since the SP10b A/B, with TWO_HANDOFF): _in_reach takes the body collider of a wave-13 Clapper
# too (its GameObject "Song Heavy Sentry (2)" / "(3)"; off: only "Song Heavy Sentry", so with two Clappers the side
# slash's reach was checked against BODY_FRONT / BODY_BACK, not the state's real span: Slam 2 / Recover front 3.37-3.49,
# Slam Antic 1.87)
REACH_NAME = _on("SSBOT_FORUM_SLAM_REACH_NAME", _V2)
NEAR_V = 0.165             # u per frame: the hero's air speed with a direction key (the probes' bounce, 9.9 u/s)
SLASH_X = (0.19, 3.12)      # the Wanderer side slash's reach in front of her box centre (knowledge/.../attacks)
BODY_FRONT, BODY_BACK = 2.25, 1.34      # the Clapper's body box from its centre (front / back), when no collider is seen


@dataclass
class PlayCfg:
    lag: int = 0                     # a mask sent for f + 2 shows in the STATE act.mask of f + 2 + lag (the probes
    #                                  that sent for the next STATE + 2 had +1, T3 LAG)
    k_jump: int = 26
    hold: int = 16
    k_down: int = 42
    k_press: int = 47
    down_after: int = 2              # down held this many frames after the press frame
    press_late_max: int = 3          # Slam 0 seen before the press: press while the frame is <= Slam 0 + this
    stand: tuple = (4.6, 5.6)        # walk until the hero's centre is in here (u in front, centre to centre)
    band: tuple = (4.0, 6.2)         # at the jump the hero must be in here, else abort (T1: 3.75-6.25 safe)
    reach: tuple = (2.7, 9.0)        # the distance at which a start is considered at all
    k_start_max: int = 14            # the latest antic frame (of the next mask) at which the script may start
    air: int = 1                     # in the air at the antic: steer toward STAND and start on landing
    k_air_max: int = 10              # ... only when seen in the air by this antic frame
    k_jump_late: int = 29            # a landing after K_JUMP - 1: the jump at once, at the latest at this frame, the
    #                                  press PRESS_AFTER frames after it but not after K_PRESS_MAX (T1, jump held 16:
    #                                  jump 28 + 20 -> 20 / 20, 29 + 18 -> 16 / 16, 30 + 20 = 51 -> 9 / 9, 31 + 20 = 52
    #                                  -> 0 / 10)
    press_after: int = 20
    k_press_max: int = 49
    k_jump_late2: int = 30           # SSBOT_FORUM_SLAM_PLAY_LATE: the latest jump of a late start (no input / airborne)
    press_after_late: int = 18       # ... its press this many frames after the jump, not after K_PRESS_MAX_LATE: SP4 t1
    k_press_max_late: int = 48       # (jump 30, press 49) landed the press at Slam 0 + 0 in 9 / 9, at Slam 0 + 1 (a
    #                                  48-frame antic) in 7 / 9 (2 hammer hits, no contact); the probes before: Slam 0
    #                                  - 2 386 / 390, - 1 27 / 27, + 0 14 / 14; T1: 29 + 18 -> 16 / 16
    k_end: int = 110                 # the script ends here at the latest
    wall_room: float = 0.5           # the stand point at least this far inside the arena walls
    over: int = 1                    # 1: the way out after the bounce (over its body, the dash); 0: no key (SP1 it1)
    over_s0: int = 20                # the direction key from Slam 0 + this
    dash_s0: int = 23                # the dash at Slam 0 + this
    over_room: float = 6.0           # behind it only with this much room from its centre to the wall (u)
    # SSBOT_FORUM_SLAM_PLAY_SIDE / _NEAR (SP5)
    side_force: int = 0              # probes: +1 keep side (in front), -1 switch side (behind), 0 the person's rule
    near_u_front: float = 3.7        # the landing, centre to centre (u): in front (its front edge 2.25 + 0.25 + 1.2)
    near_u_behind: float = 3.7       # ... behind (its turn at Idle reaches -2.25, p1 -2.87; the slash reaches 4.46)
    near_u_min: float = 3.3          # nearer when the wall leaves less room
    near_decide_s0: int = 10         # the side decided at Slam 0 + this (the mask's frame; the STATE 2 frames before:
    #                                  the lunge over, her x rel. its centre settles from STATE Slam 0 + 8)
    near_s0_behind: int = 10         # behind: the key over its body from Slam 0 + this
    near_s0_front: int = 16          # front: the key away from Slam 0 + this (the hammer / Slam Collider 2 off at +15)
    near_cross_s0: int = 40          # behind: past near_cross_u behind its centre by Slam 0 + this
    near_cross_u: float = 2.8        # 2.25 + 0.25 + 0.3
    slash_cd: int = 19               # the side slash no earlier than the down press + this (the attack cooldown)
    slash_y: float = 3.2             # ... with her y above the standing y at the mask frame + 1 at most this
    wall_pad: float = 0.45           # the landing spot's centre at least this far inside the arena walls
    # SSBOT_FORUM_SLAM_PLAY_EARLY (SP6)
    early_k_max: int = 23            # the last early press (the mask's antic frame; the person's last early press at 23)
    early_stand: tuple = (3.8, 4.8)  # the walk band while an early press is still to come (u in front, centre to centre;
    #                                  the slash meets its body front 2.25 u from its centre up to 5.37 u; from 5.0 u the
    #                                  walk into STAND after a missed last press takes 0 frames, from 3.8 u 6 frames;
    #                                  after a hit she is ~1 u farther: 4.8 + 1 inside BAND at the jump)
    early_cd: int = 19               # frames between two early presses (the Wanderer attack cooldown 0.3 s = 18 + 1)
    early_quiet: int = 3             # no key away from it this many frames before / after an early press
    early_post_stand: tuple = (4.2, 4.9)   # the walk band after an early press (the jump BAND unchanged)
    early_late_k: int = 18           # a press from this antic frame on (its recoil reaches the jump) ...
    early_late_u: float = 4.4        # ... only from this near (u, centre to centre; the walk band's top then)
    early_late_lo: float = 4.0       # ... and from this far at least (the jump BAND from early_band_lo under EARLY)
    early_min_u: float = 3.6         # no early press nearer than this, and the walk toward it stops here
    early_band_lo: float = 3.6       # under EARLY the jump band from here (SP1 it3: the jump at 3.6-7.25 u,
    #                                  71 / 71 safe)
    early_near_v: float = 0.138      # NEAR's behind clearance under EARLY: her measured air speed (u / frame) ...
    early_cross_u: float = 2.3       # ... and the distance past its centre by Slam 0 + near_cross_s0 (x at Slam 0 + 10
    #                                  <= 1.84 u in front: t1's failures 1.99 / 2.09, SP5's behind successes 0.2-2.13)

    @classmethod
    def from_env(cls) -> "PlayCfg":
        """SSBOT_FORUM_SLAM_PLAY_SET="k_jump=27,hold=15,stand=4.8:5.6" (trial variants)."""
        c = cls()
        for kv in os.environ.get("SSBOT_FORUM_SLAM_PLAY_SET", "").replace(";", ",").split(","):
            if "=" not in kv:
                continue
            k, v = (x.strip() for x in kv.split("=", 1))
            cur = getattr(c, k)
            if isinstance(cur, tuple):
                setattr(c, k, tuple(float(x) for x in v.split(":")))
            else:
                setattr(c, k, type(cur)(float(v)))
        return c


def clapper(s: dict) -> dict | None:
    return next((e for e in s.get("ents") or () if e.get("type_key") == CLAPPER and not e.get("is_dead")
                 and (e.get("hp") or 0) > 0 and e.get("pos")), None)


def clappers(s: dict) -> list[dict]:
    """Every living Clapper of a STATE (its entity order)."""
    return [e for e in s.get("ents") or () if e.get("type_key") == CLAPPER and not e.get("is_dead")
            and (e.get("hp") or 0) > 0 and e.get("pos")]


def control(e: dict | None) -> tuple[str | None, float]:
    for m in (e or {}).get("fsms") or ():
        if m.get("name") == "Control":
            return m.get("state"), float(m.get("t") or 0.0)
    return None, 0.0


FLOOR_Y = 4.568            # the hero's transform y standing on the Forum floor
GRAV = 72.0                 # u/s^2: the hero's vy falls 1.2 per frame in the air (a jump's / bounce's decay)


def _fall_frames(s: dict) -> float:
    """Frames until the hero lands on the floor in a free fall from her y / vy, 0 on the ground or below the floor. A
    rising jump counts as cut (no jump key in the land phase: the release stops the rise; the probes' hops, rising at
    17.4 at antic frame 2, landed by 18-25); a down slash's bounce (DownSpikeBounce clips) keeps its vy (it holds 17.4
    for ~8 frames, then falls 1.2 per frame: this is the earliest landing)."""
    h = s.get("hero") or {}
    y = float((h.get("pos") or [0.0, FLOOR_Y])[1]) - FLOOR_Y
    if y <= 0.0:
        return 0.0
    vy = float((h.get("vel") or [0.0, 0.0])[1])
    if not str((h.get("anim") or {}).get("clip") or "").startswith("DownSpikeBounce"):
        vy = min(vy, 0.0)
    return 60.0 * (vy + (vy * vy + 2.0 * GRAV * y) ** 0.5) / GRAV


def hero_x(s: dict) -> float:
    h = s.get("hero") or {}
    b = h.get("box")
    return 0.5 * (float(b[0]) + float(b[2])) if b else float(h["pos"][0])


_GROUND_BIT: list = []


def on_ground(s: dict) -> bool:
    """The hero's cState.onGround from a raw STATE (the facts' cstate schema; the probes, which have no WorldState)."""
    if not _GROUND_BIT:
        _GROUND_BIT.append(kin.cstate_names().index("onGround"))
    cs = (s.get("hero") or {}).get("cstate")
    i = _GROUND_BIT[0]
    return bool(cs) and bool((int(cs[i >> 6]) >> (i & 63)) & 1)


@dataclass
class Run:
    """One slam the playbook looked at."""
    iid: object
    fa: int                          # the antic entry frame (STATE frames: reports)
    face: int                        # the Clapper's facing (+1: right)
    ta: float = 0.0                  # the antic entry on the game clock (s): the script's frames k count game frames
    phase: str = "wait"              # wait (conditions not yet met) / walk / jump / air / after / done / abort
    why: str = ""
    k_start: int | None = None
    x_start: float | None = None
    k_jump: int | None = None        # the frame the jump was sent for
    x_jump: float | None = None
    k_press: int | None = None
    s0: int | None = None            # the Slam 0 entry frame (first STATE seen)
    ks0: int | None = None           # Slam 0's entry as a game frame from the antic entry
    k: int = 0                       # the frame k of the latest tick (the decision log)
    hp0: int | None = None
    bounced: bool = False
    over_dir: int | None = None      # the way out: +1 / -1 world x, 0 none
    k_dash: int | None = None
    k_air: int | None = None         # the frame the airborne entry took over (phase land)
    k_press_plan: int | None = None  # the press frame for this run's jump (K_PRESS, later after a late jump)
    stand: tuple | None = None       # this run's stand / band when not the cfg's (SSBOT_FORUM_JUMP_BEHIND near a wall)
    band: tuple | None = None
    late: bool = False               # SSBOT_FORUM_SLAM_PLAY_LATE: no input seen at the antic (a late start allowed)
    side_why: str = ""               # SP5: why this side (wall / two / force / room / clear / old)
    near: int | None = None          # SP5 NEAR: the way's world direction (+-1), 0 = the old way out, None = not decided
    near_u: float = 0.0              # ... the landing's distance from its centre on that side
    k_turn: int | None = None        # ... the frame of the turn key (she faces it)
    k_slash: int | None = None       # ... the side slash's press frame
    k_early: list = field(default_factory=list)   # SP6 EARLY: the early side slashes' press frames (antic frame k)
    sent: list = field(default_factory=list)   # (frame, mask)
    handoff: bool = False            # SP10b TWO_HANDOFF: opened right after a strike run on the other Clapper closed
    ho_cand: bool = False            # ... (pending: decided on the run's first tick from its antic frame)
    tight: tuple | None = None       # SP10b TWO_TIGHT: (the other's iid, the way's world direction, 0 = no room / reach)
    chain: object = None             # SP10b TWO_AIRCHAIN: the air chain's plan (air_chain.Plan) while it runs
    chain_off: str = ""              # ... why the chain is no longer tried on this run ("" = may still start)
    chain_next: int = 0              # ... the next frame a failed search is tried again
    chain_from: object = None        # ... a run on B opened by the chain's strike: A's iid
    chain_log: list = field(default_factory=list)   # [frame, event, plan row]
    rg_k: int | None = None          # SP11-0 TWO_RUNEGATE: the antic frame it started where the old gate declined
    cs: object = None                # SP13 SSBOT_FORUM_CLAWSTRIKE: the Clawline plan (claw_strike.CsPlan) once taken
    cs_toward: int = 0               # ... the world direction toward S
    cs_k_press: int | None = None    # ... the Clawline's antic frame (sent)
    cs_k_ctrl: int | None = None     # ... control's antic frame
    cs_strike: object = None         # ... the strike's plan (air_chain.Plan) from control
    cs_log: list = field(default_factory=list)   # [frame, event, data]
    cs_hit: bool = False             # ... a hit on S after the strike's press (the strike's bounce)
    cs_next: int = 0                 # ... a failed Clawline search is tried again from this mask frame
    as_air: bool = False             # SP13a SSBOT_FORUM_AIRSTRIKE: the strike planned from the air (air_chain.search)


class SlamPlay:
    def __init__(self, cfg: PlayCfg | None = None):
        self.cfg = cfg or PlayCfg.from_env()
        self.run: Run | None = None
        self.done: list[Run] = []            # finished runs of this episode (the stats)
        self._closed_iid = None              # the Clapper whose slam was handled: no second look until it leaves it
        self._closed: set = set()            # TWO_PLAY: every Clapper whose slam was handled (until it leaves it)
        self._closed_ta: dict = {}           # Clapper iid -> the handled slam's antic entry (clock): its identity
        self._jfam: dict = {}                # TWO_PLAY: Clapper iid -> "j" / "jc" (its jump move) / "jc_landed"
        self._rune: dict = {}                # TWO_PLAY: Clapper iid -> (landing x, facing, game time) of a jump cast
        self._t = 0.0                        # SP10b: this tick's clock (s)
        self._ho = None                      # SP10b TWO_HANDOFF: (iid, clock) of the last strike run closed
        self._hold = None                    # SP10b TWO_TIGHT: (B's iid, clock, HP) - no key until B's Slam 2
        self.holds: list = []                # ... [B iid, start f, end f, why] per hold (stats)
        self._guard = None                   # SP11-0 TWO_GUARD: this tick's danger spans (combat.two_play)
        self._rg_circ: dict = {}             # SP11-0 TWO_RUNEGATE: circle iid -> {t0, lit, burst, cx}
        self._rg_tick = None                 # ... this tick's antic frame when the old gate would have declined
        self.side_hint: dict = {}            # SP11b TWO_PUSHMID: Clapper iid -> the world side of its way out
        self._bombs = None                   # SP12a TWO_STRIKEGUARD: this tick's bomb forecast (rune_bombs.frames)
        self.sg: list = []                   # ... [iid, antic entry, k, why, decline / abort, ticks] per guard event
        self._csx = None                     # SP13 SSBOT_FORUM_CLAWSTRIKE: claw_strike.ClawStrike (made on first use)
        self.cs_declines: dict = {}          # ... why a slam the playbook could not reach got no Clawline
        self._life = _rl.RuneCircles()       # the rune circles' lives (shared with the other scripts by the policy)

    def reset(self) -> None:
        self.run = None
        self.done = []
        self._closed_iid = None
        self._closed, self._jfam, self._rune = set(), {}, {}
        self._closed_ta = {}
        self._ho = self._hold = None
        self.holds = []
        self._rg_circ = {}
        self.side_hint = {}
        self._bombs = None
        self.sg = []
        self.cs_declines = {}
        self._life = _rl.RuneCircles()

    def _two_pick(self, s: dict, t: float) -> dict | None:
        """TWO_PLAY: the Clapper of this tick - the run's while it lives, else one entering a slam it has not handled
        (the nearest to the hero), else the first not handled; the per-Clapper bookkeeping (handled slams, jump casts'
        landings for the rune circle)."""
        cs = clappers(s)
        for o in cs:
            st = control(o)[0]
            iid = o.get("iid")
            if st not in SLAM_STATES and (self.run is None or self.run.iid != iid):
                self._closed.discard(iid)
            elif st == "Slam Antic" and iid in self._closed and self._new_slam(iid, t - control(o)[1]):
                self._closed.discard(iid)
            if st in ("Cast Slam Antic", "Cast Slam Antic 2"):
                self._jfam[iid] = "jc"
                self._rune.pop(iid, None)
            elif st == "Jump Antic":
                self._jfam[iid] = "j"
            elif st in ("Slam 2", "Slam Recover", "Idle") and self._jfam.get(iid) == "jc":
                self._jfam[iid] = "jc_landed"
                self._rune[iid] = (float(o["pos"][0]), 1 if o.get("flipX") else -1, t)
            elif st in ("Slam Antic", "Spell Antic", "Evade Scuttle"):
                self._jfam.pop(iid, None)
        if self.run is not None:
            return next((o for o in cs if o.get("iid") == self.run.iid), None)
        hx = hero_x(s) if (s.get("hero") or {}).get("box") or (s.get("hero") or {}).get("pos") else 0.0
        antic = [o for o in cs if control(o)[0] == "Slam Antic" and o.get("iid") not in self._closed]
        if antic:
            return min(antic, key=lambda o: abs(float(o["pos"][0]) - hx))
        return next((o for o in cs if o.get("iid") not in self._closed), None)

    def _rg_exposed(self, rc: tuple, tx: float, t: float, k: int) -> bool:
        """SSBOT_FORUM_TWO_RUNEGATE: the strike started now (antic frame k) meets the circle of the jump cast that landed
        at rc (x, facing, clock) while it is lit (module constants); False once that circle burst."""
        cen = rc[0] + rc[1] * (RG_C[1] if rc[1] > 0 else RG_C[0])
        for c in self._rg_circ.values():
            if c["burst"] and abs(c["cx"] - cen) < 1.5 and c["t0"] >= rc[2] - 0.1:
                return False
        w0, w1 = rc[2] + (RG_LIT[0] - RG_M) / 60.0, rc[2] + (RG_LIT[1] + RG_M) / 60.0
        if t > w1:
            return False
        dx = max(0.0, abs(tx - cen) - 0.23)
        for kk in range(max(k, k + int((w0 - t) * 60.0)), min(110, k + int(round((w1 - t) * 60.0))) + 1):
            hb = RG_H10[min(kk // 2, len(RG_H10) - 1)]
            if dx * dx + max(0.0, hb - 0.34) ** 2 < RG_R * RG_R:
                return True
        return False

    def _rg_observe(self, s: dict, t: float) -> None:
        """SSBOT_FORUM_TWO_RUNEGATE: the circle objects' first time, lit and burst (lit, then unlit) every tick."""
        from ssbot.combat import cast_stab as _cs
        for lo, hi, ciid, lit in _cs.rune_spans(s):
            c = self._rg_circ.setdefault(ciid, {"t0": t, "lit": False, "burst": False, "cx": 0.5 * (lo + hi)})
            if abs(c["cx"] - 0.5 * (lo + hi)) > 0.5 or (c["burst"] and lit):
                c.update(t0=t, lit=False, burst=False, cx=0.5 * (lo + hi))     # the pool reused the object
            if lit:
                c["lit"] = True
            elif c["lit"]:
                c["burst"] = True

    def _two_danger(self, s: dict, e: dict, tx: float, t: float, k: int | None = None) -> str | None:
        """TWO_PLAY: why the other Clapper can reach the stand point tx during the strike (module constants), or None.
        k: the antic frame of this tick's mask (SSBOT_FORUM_TWO_RUNEGATE's rune check; None: the old one)."""
        for o in clappers(s):
            if o.get("iid") == e.get("iid"):
                continue
            st = control(o)[0]
            d = abs(float(o["pos"][0]) - tx)
            if st in TWO_JUMP_ST:
                return f"other {st}"
            if st in ("Slam 0", "Slam 1", "Slam Effects?", "Slam 2") and d < TWO_SLAM_U:
                return f"other {st}"
            if st in ("Spell Antic", "Cast 1", "Cast 2") and d < TWO_CAST_U:
                return f"other {st}"
            if st == "Slam Recover" and d < TWO_BODY_U:
                return "other Slam Recover"
            rc = self._rune.get(o.get("iid"))
            if rc is not None and TWO_RUNEGATE and k is not None:
                if self._rg_exposed(rc, tx, t, k):
                    return "other rune circle"
                if t <= rc[2] + TWO_RUNE[2] and TWO_RUNE[0] <= (tx - rc[0]) * rc[1] <= TWO_RUNE[1]:
                    self._rg_tick = k                 # the old gate would have declined this tick (stats)
            elif rc is not None and t <= rc[2] + TWO_RUNE[2] and TWO_RUNE[0] <= (tx - rc[0]) * rc[1] <= TWO_RUNE[1]:
                return "other rune circle"
        return None

    def stats(self) -> dict:
        from collections import Counter
        out = Counter()
        for r in self.done + ([self.run] if self.run is not None else []):
            out["slams"] += 1
            out[f"end_{r.phase}"] += 1
            if r.k_start is not None:
                out["started"] += 1
            if r.k_press is not None:
                out["pressed"] += 1
            if r.bounced:
                out["bounced"] += 1
            if r.k_dash is not None:
                out["dashed"] += 1
            if r.k_air is not None:
                out["air_entry"] += 1
            if r.phase == "abort" or (r.phase == "wait" and r.why):
                out[f"why_{r.why}"] += 1
            if r.over_dir is not None or r.near:
                d = r.near if r.near else r.over_dir
                out["side_" + ("front" if d == r.face else "behind" if d == -r.face else "none")] += 1
                if r.side_why:
                    out[f"side_why_{r.side_why}"] += 1
            if r.k_slash is not None:
                out["near_slash"] += 1
            if r.k_early:
                out["early_runs"] += 1
                out["early_press"] += len(r.k_early)
            if r.handoff:
                out["handoff"] += 1
                out["handoff_pressed"] += r.k_press is not None
            if r.tight is not None:
                out["tight_" + ("away" if r.tight[1] else "noroom")] += 1
            if r.chain_log:
                out["chain_runs"] += 1
                for ev in r.chain_log:
                    out["chain_" + ev[1]] += 1
            if r.chain_from is not None:
                out["chain_b_runs"] += 1
                out["chain_b_bounced"] += r.bounced
        if self.holds:
            out["tight_holds"] = len(self.holds)
        if _cs.CLAWSTRIKE or _cs.AIRSTRIKE:
            for r in self.done + ([self.run] if self.run is not None else []):
                if r.as_air:
                    out["as_runs"] += 1
                    out["as_pressed"] += r.k_press is not None
                    out["as_hit"] += r.cs_hit
                    out[f"as_end_{r.phase}_{r.why[:24]}"] += 1
                if r.cs is None:
                    continue
                out["cs_runs"] += 1
                out["cs_pressed"] += r.cs_k_press is not None
                out["cs_ctrl"] += r.cs_k_ctrl is not None
                out["cs_struck"] += r.cs_strike is not None and r.k_press is not None
                out["cs_hit"] += r.cs_hit
                out[f"cs_end_{r.phase}_{r.why[:24]}"] += 1
            for why, n in self.cs_declines.items():
                out[f"cs_no_{why}"] += n
        rg = [[r.iid, r.fa, r.rg_k, r.phase, r.why, r.k_press, r.bounced]
              for r in self.done + ([self.run] if self.run is not None else []) if r.rg_k is not None]
        res = dict(out)
        if rg:
            res["rg_rel"] = rg                       # SP11-0 TWO_RUNEGATE: the runs its gate let start
        if STRIKEGUARD:
            res["sg"] = [list(x) for x in self.sg]   # SP12a TWO_STRIKEGUARD: its declines / aborts
        return res

    def runs_rec(self) -> list:
        """SP10a (logging only): every run - [iid, antic entry frame, phase, why, k_start, k_jump, k_press, bounced,
        Slam 0's k, k_air, the last tick's k, side_why]."""
        # SP10b: + [handoff, tight (other iid, way) or None, k_slash] (only when one of them is set: the old rows keep
        # their length)
        out = []
        for r in self.done + ([self.run] if self.run is not None else []):
            row = [r.iid, r.fa, r.phase, r.why, r.k_start, r.k_jump, r.k_press, r.bounced, r.ks0, r.k_air, r.k,
                   r.side_why]
            if r.handoff or r.tight is not None or r.chain_log or r.chain_from is not None or r.cs_log:
                row += [r.handoff, None if r.tight is None else list(r.tight), r.k_slash, r.chain_log,
                        r.chain_from]
            if r.cs_log:
                # SP13 SSBOT_FORUM_CLAWSTRIKE: [the plan, the log, the Clawline's / control's antic frames, the strike]
                row += [None if r.cs is None else r.cs.row(), r.cs_log, r.cs_k_press, r.cs_k_ctrl,
                        None if r.cs_strike is None else r.cs_strike.row(), r.as_air]
            out.append(row)
        return out

    def active(self) -> bool:
        return self.run is not None and self.run.phase in ("land", "walk", "jump", "air", "after", "cs_pre", "cs_lock",
                                                            "cs_strike")

    def abort(self, why: str) -> None:
        """Hand the slam back to the planner (the supervisor took the keys)."""
        if self.active():
            self._close("abort", why)
        elif self.run is not None and self.run.phase == "wait":
            self.run.why = why

    def _close(self, phase: str, why: str = "") -> None:
        r = self.run
        if r is not None:
            if TWO_HANDOFF and TWO_PLAY and phase == "done" and r.k_press is not None:
                self._ho = (r.iid, self._t)          # SP10b: the other one's slam may be handed over (step)
            if r.phase in ("walk", "jump", "air", "after") or phase == "abort":
                r.phase = phase
            r.why = r.why or why
            self.done.append(r)
            self._closed_iid = r.iid
            self._closed_ta[r.iid] = r.ta
            if TWO_PLAY:
                self._closed.add(r.iid)
        self.run = None

    def _new_slam(self, iid, ta: float) -> bool:
        """Task 179 #303 (live 179-L1 w13_walk179 8f9e9629, 2683): the handled mark names a slam, not a Clapper. The
        script is not stepped while the B2 chain owns the keys, so it never saw 335476 leave the slam handed over at
        2526 and took its new Slam Antic (2675) for the handled one. An antic entry more than 30 frames from the handled
        one (step's new_antic rule) is a new slam; the handled slam itself still gets no second look."""
        done = self._closed_ta.get(iid)
        return done is not None and abs(ta - done) * 60.0 > 30

    def step(self, f: int, s: dict, ground: bool, accepting: bool = True, t_game: float | None = None,
             skip: frozenset | None = None, sim=None, guard: list | None = None, bombs=None) -> int | None:
        """The mask for frame f + 2 from the STATE of frame f, or None (the planner decides).

        t_game: the game clock (s; the backend's Stamp.t_game_s, the sum of the scaled dt: it stands still through
        hit-stop freezes and pauses). The script's frames k count game frames from the antic entry (its Control state
        time): a freeze in the slam (SP2: a hit that takes the Clapper across 80 / 50 / 20 HP freezes the game for
        ~12 frames) no longer moves the jump and the press ahead of the Clapper. None: the STATE frame f is the clock
        (the frame count of SP1)."""
        c = self.cfg
        t = f / 60.0 if t_game is None else float(t_game)
        self._t = t
        self._guard = guard                  # SP11-0 SSBOT_FORUM_TWO_GUARD: the other one's danger spans (or None)
        self._bombs = bombs                  # SP12a SSBOT_FORUM_TWO_STRIKEGUARD: rune_bombs.frames from this STATE (or None)
        self._f = f
        self._life.update(f, s, t)
        e = self._two_pick(s, t) if TWO_PLAY else clapper(s)
        if (TWO_RUNEGATE and TWO_PLAY) or _cs.CLAWSTRIKE:
            self._rg_observe(s, t)                    # (SP13: the circles' burst for the Clawline's gate)
        if self._hold is not None:
            hm = self._hold_mask(f, s)
            if hm is not None:
                return hm
        if skip and e is not None and e.get("iid") in skip:
            # SP9c (combat.two_play's antic switch): its slam is left alone (she switched to the other one)
            if self.run is not None and self.run.iid in skip:
                self._close("abort", "asw")
            return None
        st, tin = control(e)
        r = self.run
        ta = (f - round(tin * 60.0)) / 60.0 if t_game is None else t - tin     # this antic's entry on the clock
        new_antic = r is not None and st == "Slam Antic" and abs(ta - r.ta) * 60.0 > 30
        if r is not None and (e is None or e.get("iid") != r.iid or new_antic or (
                st not in SLAM_STATES and not (r.phase == "after" and r.bounced))):
            # the slam ended (or the Clapper is gone, or a new slam began): a finished script is done, an unstarted
            # look is dropped; the way out after a bounce runs on to the landing
            self._close("done" if r.phase in ("after", "air", "jump") else r.phase, "slam over")
            r = None
            if new_antic:
                self._closed_iid = None
        if (st not in SLAM_STATES or (e is not None and e.get("iid") != self._closed_iid)
                or (st == "Slam Antic" and self._new_slam(self._closed_iid, ta))):
            self._closed_iid = None
        if r is None:
            if st != "Slam Antic" or (e is not None and e.get("iid") == self._closed_iid):
                return None
            face = 1 if e.get("flipX") else -1
            r = self.run = Run(iid=e.get("iid"), fa=int(f - round(tin * 60.0)), face=face, ta=ta)
            if (TWO_HANDOFF and TWO_PLAY and self._ho is not None and self._ho[0] != r.iid
                    and (t - self._ho[1]) * 60.0 <= HO_GAP_F):
                r.ho_cand = True                          # SP10b: a strike run on the other one just closed
        if r.phase in ("done", "abort"):
            return None
        h = s.get("hero") or {}
        hp = int(h.get("health") or 0)
        if st == "Slam 0" and r.s0 is None:
            r.s0 = f
            r.ks0 = int(round(((t if t_game is None else t - tin) - r.ta) * 60.0))
        k = int(round((t - r.ta) * 60.0)) + SEND_AHEAD + c.lag     # the antic frame this tick's mask lands on
        r.k = k
        if r.ho_cand:
            # SP10b TWO_HANDOFF: B's run as a late start (the jump up to K_JUMP_LATE2) when its antic frame allows it
            r.ho_cand = False
            if LATE and k <= c.k_jump_late2 and r.phase == "wait":
                r.late = r.handoff = True
        if r.hp0 is not None and hp < r.hp0:
            self._close("abort", "hurt")
            return None
        if r.phase in ("cs_pre", "cs_lock", "cs_strike"):
            # SP13 SSBOT_FORUM_CLAWSTRIKE: the Clawline approach holds the keys
            return self._cs_step(r, k, f, s, e, ground, accepting, sim, t)
        if r.phase == "land" and ground:
            r.phase = "wait"                              # landed: the start check (walk time from here)
        if r.phase == "land":
            if ((_cs.CLAWSTRIKE or _cs.AIRSTRIKE) and sim is not None and accepting
                    and (k > (c.k_jump_late2 if LATE else c.k_jump_late - 1)
                         or (LATE and k + _fall_frames(s) > c.k_jump_late2) or self._cs_cfg().trigger == "force")):
                # SP13: no landing in time for the ground strike (or the trials' force): the Clawline approach
                cm = self._cs_try(r, k, f, s, e, ground, accepting, sim, hp, t, "no landing")
                if cm is not None:
                    return cm
            if k > (c.k_jump_late2 if LATE else c.k_jump_late - 1) or (not accepting and not LATE):
                self._close("abort", "no landing" if accepting else "no input in the air")
                return None
            if LATE and k + _fall_frames(s) > c.k_jump_late2:
                # SSBOT_FORUM_SLAM_PLAY_LATE: even a free fall from here lands after K_JUMP_LATE2 (a pogo bounce off its
                # head, SP4 t3: 9 u above the floor at the antic): hand the slam back at once, not at frame 30
                self._close("abort", "no landing (fall)")
                return None
            m = self._walk(s, float(e["pos"][0]), r.face, f)
            r.sent.append((f + SEND_AHEAD, m))
            return m
        if r.phase == "wait":
            self._rg_tick = None
            if TWO_PLAY:
                # SP7: not while the other Clapper can reach the stand point during the strike (the planner decides)
                cx0 = float(e["pos"][0])
                x0 = (hero_x(s) - cx0) * r.face
                tx = cx0 + r.face * min(max(x0, c.stand[0]), c.stand[1])
                why = self._two_danger(s, e, tx, t, k)
                if why is None and STRIKEGUARD:
                    why = self._sg_danger(s, e, r, tx, k, walk=False)
                    if why is not None:
                        self._sg_log(r, k, why, "decline")
                if why is not None:
                    r.why = why
                    return None
            # Task 182 seq 310: any rune placed by anyone, its own Clapper's too (with one Clapper as well)
            cx0_ = float(e["pos"][0])
            why = self._rune_path(s, cx0_ + r.face * min(max((hero_x(s) - cx0_) * r.face, c.stand[0]), c.stand[1]), k)
            if why is not None:
                r.why = why
                return None
            if _cs.CLAWSTRIKE and sim is not None and self._cs_cfg().trigger == "force":
                # SP13 fixed-point trials: the Clawline approach on every slam it can reach from force_min_u
                if (hero_x(s) - float(e["pos"][0])) * r.face >= self._cs_cfg().force_min_u:
                    cm = self._cs_try(r, k, f, s, e, ground, accepting, sim, hp, t, "force")
                    if cm is not None:
                        return cm
            m = self._try_start(r, k, s, e, ground, accepting, hp, f)
            if m is not None and TWO_RUNEGATE and self._rg_tick == k and r.rg_k is None:
                r.rg_k = k                            # SP11-0: started where the old gate would have declined it
            if m is None:
                if ((_cs.CLAWSTRIKE or _cs.AIRSTRIKE) and sim is not None and self.run is r and r.phase == "wait"
                        and (r.why == "no time to walk" or r.why == "in the air"
                             or (r.why.startswith("distance") and (hero_x(s) - float(e["pos"][0])) * r.face
                                 > c.reach[1]))):
                    # SP13: the ground strike cannot reach it in time: the Clawline approach
                    cm = self._cs_try(r, k, f, s, e, ground, accepting, sim, hp, t, r.why.split(" ")[0])
                    if cm is not None:
                        return cm
                return None
            if EARLY and k < c.k_jump and r.phase == "walk":
                m = self._early(r, k, f, s, e, float(e["pos"][0]), ground, m)   # SP6: no key away before a press
            if k < c.k_jump or r.phase == "land":
                # (SP10b: a late start in the air from K_JUMP on steers toward STAND like any land phase; it fell
                # through to the after-the-press branch before and raised on k_press None - only reachable with a
                # LATE start in the air at k >= K_JUMP, which the old paths almost never met)
                r.sent.append((f + SEND_AHEAD, m))
                return m
            # a late landing inside the jump band: the jump this tick (below)
        cx = float(e["pos"][0])
        x = (hero_x(s) - cx) * r.face                     # in front: > 0
        if r.phase == "walk" and k < c.k_jump:
            # Task 182 seq 310: the walk goes on only while its way and the strike's stand are clear of the placed runes (a run started
            # before the circle was there, or before a bomb was forecast). Nothing here looks at the owner of a rune.
            tx_ = cx + r.face * min(max(x, (r.stand or c.stand)[0]), (r.stand or c.stand)[1])
            why = self._rune_path(s, tx_, k)
            if why is not None:
                self._close("abort", "rune " + why)
                return None
        if r.phase == "walk" and STRIKEGUARD and k < c.k_jump and TWO_PLAY:
            # SP12a: the other one's danger reaches the strike's path during the walk: the planner decides
            tx_ = cx + r.face * min(max(x, (r.stand or c.stand)[0]), (r.stand or c.stand)[1])
            why = self._sg_danger(s, e, r, tx_, k, walk=True)
            if why is not None:
                self._sg_log(r, k, why, "abort")
                self._close("abort", "sg " + why)
                return None
        if r.phase == "walk":
            band = r.band or c.band
            if EARLY:
                band = (min(band[0], c.early_band_lo), band[1])     # SP6: an early hit's knock-back builds up late
            late_walk = (LATE and (r.k_air is not None or r.late) and k < c.k_jump_late2 and ground
                         and not band[0] <= x <= band[1])
            if k < c.k_jump or late_walk:
                m = self._walk(s, cx, r.face, f)          # (LATE: a late start walks into the band up to K_JUMP_LATE2)
                if EARLY and k < c.k_jump:
                    m = self._early(r, k, f, s, e, cx, ground, m)   # SP6: side slashes in the early antic
            else:
                if not ground:
                    self._close("abort", "not on the ground at the jump")
                    return None
                if not band[0] <= x <= band[1]:
                    self._close("abort", f"x {x:.2f} outside the band at the jump")
                    return None
                if k > (c.k_jump_late2 if LATE else c.k_jump_late):
                    self._close("abort", "late jump")
                    return None
                r.phase, r.k_jump, r.x_jump = "jump", k, round(x, 3)
                if LATE:
                    # SSBOT_FORUM_SLAM_PLAY_LATE: every press by Slam 0 - 1 (K_PRESS_MAX_LATE), 18 frames after a late
                    # jump (a jump at K_JUMP still presses at K_PRESS)
                    r.k_press_plan = min(max(c.k_press, k + c.press_after_late), c.k_press_max_late)
                else:
                    r.k_press_plan = min(max(c.k_press, k + c.press_after), c.k_press_max)
                m = M_J
        elif r.phase == "jump":
            m = M_J if k < r.k_jump + c.hold else 0
            if k >= r.k_jump + c.hold:
                r.phase = "air"
            m = self._press_part(r, k, m)
            if m is None:
                return None
        elif r.phase == "air":
            m = self._press_part(r, k, 0)
            if m is None:
                return None
        else:                                             # after the press: never the jump
            if not r.bounced:
                if r.cs is not None or r.as_air:
                    # SP13: the Clawline's own bounce rises at the press: the strike's bounce is its hit on S
                    if self._cs_s_hit(s, r):
                        r.bounced = r.cs_hit = True
                    elif k > r.k_press + 14:
                        self._close("abort", "no bounce")
                        return None
                elif float((h.get("vel") or [0, 0])[1]) > 6.0:
                    r.bounced = True
                elif k > r.k_press + 14:
                    self._close("abort", "no bounce")
                    return None
            if ground and k > r.k_press + 8:
                tight = r.tight
                self._close("done", "landed")
                if tight is not None and tight[1]:
                    # SP10b TWO_TIGHT: landed on A's far side - no key until B's Slam 2 (the planner's jump toward B)
                    self._hold = (tight[0], t, hp, f)
                    hm = self._hold_mask(f, s)
                    if hm is not None:
                        return hm
                if TWO_HANDOFF and TWO_PLAY:
                    # SP10b: B's run opens on this tick (a late start)
                    return self.step(f, s, ground, accepting, t_game, skip, sim, guard)
                return None
            if (_ac.AIRCHAIN and TWO_PLAY and sim is not None and r.bounced and r.s0 is not None and not r.chain_off
                    and not (r.tight is not None and r.tight[1])):
                cm = self._chain(r, k, f, s, e, t, sim, hp)
                if cm is not None:
                    return cm
            if TWO_TIGHT and TWO_PLAY and r.tight is None and r.bounced and r.s0 is not None and r.chain is None:
                self._tight_check(r, k, s, e, cx, t)
            m = 0
            if k <= r.k_press + c.down_after:
                m = M_D
            if NEAR and c.over and r.bounced and r.s0 is not None and r.near != 0:
                m |= self._near(r, k, f, s, e, cx)          # SP5: the closer landing, the side slash before it
            elif c.over and r.bounced and r.s0 is not None and k - r.ks0 >= c.over_s0:
                if r.over_dir is None:
                    r.over_dir = self._side_old(r, s, e, cx) if SIDE else self._over_dir(cx, r.face)
                if r.over_dir:
                    m |= M_R if r.over_dir > 0 else M_L
                    ks0 = k - r.ks0
                    if r.k_dash is None and ks0 >= c.dash_s0:
                        r.k_dash = k
                    if r.k_dash is not None and k < r.k_dash + 2:
                        m |= M_DASH
        if k > c.k_end:
            self._close("done", "k_end")
            return None
        r.sent.append((f + SEND_AHEAD, m))
        return m

    # ---- SP10b ----

    def _ho_aim(self, r: Run, s: dict, cx: float, d: int) -> None:
        """TWO_HANDOFF: another Clapper in Slam Antic on the landing's side (between them): the landing at its stand
        (HO_STAND_U in front of its centre) when that is farther from A than the run's near_u (the room permitting)."""
        for o in clappers(s):
            if o.get("iid") == r.iid or control(o)[0] != "Slam Antic" or o.get("iid") in self._closed:
                continue
            u = (float(o["pos"][0]) - cx) * d - HO_STAND_U
            if u > r.near_u + 0.05:
                fit = self._near_fit(d, cx, u)
                if fit is not None and fit > r.near_u:
                    r.near_u = fit
                    r.side_why = "ho_aim"
            return

    def _guarded_spot(self, r: Run, x: float) -> bool:
        """SP11-0 SSBOT_FORUM_TWO_GUARD: her landing at x (box centre) meets another Clapper's danger span (its jump
        landing band, its big rune circle; not its slam: the hand-off / TWO_TIGHT handle a second hammer)."""
        from ssbot.combat import two_play as _tp
        if STRIKEGUARD and SG_BOMBS and self._sg_bomb_at(r, x, SG_LAND_K):
            return True                              # SP12a: a bomb of the other one lit at her landing
        return _tp.guard_hit(self._guard, x - 0.25, x + 0.25, kinds=("land", "rune"), own=r.iid) is not None

    # ---- SP12a SSBOT_FORUM_TWO_STRIKEGUARD ----

    def _sg_k0(self, r: Run) -> int:
        """The antic frame of this tick's STATE (the bomb frames count from it)."""
        return int(round((self._t - r.ta) * 60.0))

    def _sg_bomb_at(self, r: Run, x: float, ks: tuple, h: float = 0.0) -> bool:
        """A bomb of a Clapper other than the run's lit over her box (centre x, box bottom h above the floor) at some
        antic frame of [ks[0], ks[1]]."""
        bk = getattr(self, "_bombs", None)
        if bk is None or not len(bk):
            return False
        import numpy as np
        from ssbot.combat import rune_bombs as _rb
        own = {int(o) for o in bk[:, 0] if int(o) != r.iid}
        if not own:
            return False
        k0 = self._sg_k0(r)
        kk = np.arange(ks[0], ks[1] + 1) - k0
        y = 3.0 + h + 1.0394                      # Bounds centre (the kinematics box: half height 1.0394)
        return bool(_rb.occupied(bk, np.full(kk.shape, x), np.full(kk.shape, y), kk, SG_BOMB_M, own).any())

    def _sg_danger(self, s: dict, e: dict, r: Run, tx: float, k: int, walk: bool) -> str | None:
        """SSBOT_FORUM_TWO_STRIKEGUARD: why the other Clapper's danger reaches the strike's path from antic frame k
        (module constants), or None."""
        import numpy as np
        hx = hero_x(s)
        lo, hi = min(hx, tx) - 0.25, max(hx, tx) + 0.25
        for o in clappers(s):
            if o.get("iid") == e.get("iid"):
                continue
            from ssbot.combat import two_play as _tp
            a, b = _tp.body_span(o)
            if a - SG_BODY_PAD < hi and b + SG_BODY_PAD > lo:
                return "other body"
            if walk:
                st = control(o)[0]
                if st in TWO_JUMP_ST:
                    return f"other {st}"
                if st in ("Spell Antic", "Cast 1", "Cast 2") and abs(float(o["pos"][0]) - tx) < TWO_CAST_U:
                    return f"other {st}"
        bk = getattr(self, "_bombs", None) if SG_BOMBS else None
        if bk is not None and len(bk):
            from ssbot.combat import rune_bombs as _rb
            own = {int(o_) for o_ in bk[:, 0] if int(o_) != r.iid}
            if own:
                k0 = self._sg_k0(r)
                ks = np.arange(max(k, k0), SG_END_K + 1)
                kj = max(k, self.cfg.k_jump)
                d = 1.0 if tx >= hx else -1.0
                xs = np.where(ks < kj, hx + d * np.minimum(abs(tx - hx), WALK_U * (ks - k0)), tx)
                hs = np.array([0.0 if kk < kj else RG_H10[min(int(kk) // 2, len(RG_H10) - 1)] for kk in ks])
                ys = 3.0 + hs + 1.0394
                if _rb.occupied(bk, xs, ys, ks - k0, SG_BOMB_M, own).any():
                    return "other bomb"
        return None

    def _rune_path(self, s: dict, tx: float, k: int) -> str | None:
        """Task 182 seq 310: why the strike's way (from her x to the stand point tx at the walk, then the jump of RG_H10 from K_JUMP) meets a placed
        rune on the rune's own lit frames, or None: every big circle (rune_life.RuneCircles, its Clapper's own last jump cast included) and
        every small rune of the forecast (self._bombs). k: the antic frame of this tick's mask. Its time matters: a circle that burns out before she
        gets there blocks nothing."""
        import numpy as np
        rows = self._life.rows()
        bk = self._bombs
        if bk is not None and len(bk):
            rows = np.concatenate([rows, np.asarray(bk, np.float64).reshape(-1, 6)]) if len(rows) else np.asarray(bk, np.float64).reshape(-1, 6)
        if not len(rows):
            return None
        c = self.cfg
        h = s.get("hero") or {}
        hx0 = hero_x(s)
        vx = float((h.get("vel") or [0.0, 0.0])[0])
        n = int(min(float(rows[:, 5].max()), _rl.HORIZON)) + 2
        j = np.arange(n + 1)
        x_mask = hx0 + vx * SEND_AHEAD / 60.0
        d = tx - x_mask
        xs = np.where(j < SEND_AHEAD, hx0 + vx * j / 60.0, x_mask + np.sign(d) * np.minimum(abs(d), WALK_U * (j - SEND_AHEAD)))
        kk = k - SEND_AHEAD + j
        tab = np.asarray(RG_H10, np.float64)
        bottom = np.where(kk < c.k_jump, 0.0, tab[np.minimum(kk // 2, len(tab) - 1).astype(np.int64)])
        return _rl.path_exposed(xs, bottom, rows)

    def _sg_log(self, r: Run, k: int, why: str, what: str) -> None:
        if what == "decline" and self.sg and self.sg[-1][0] == r.iid and self.sg[-1][1] == r.fa and                 self.sg[-1][4] == "decline":
            self.sg[-1][5] += 1                    # the same slam declined again this tick
            return
        self.sg.append([r.iid, r.fa, k, why, what, 1])

    def _hold_mask(self, f: int, s: dict) -> int | None:
        """TWO_TIGHT's hold after the far-side landing: 0 (no key) while B is in its slam before Slam 2, she is not hurt
        and TIGHT_HOLD_S has not passed; else the hold ends (None)."""
        iid, t0, hp0, f0 = self._hold
        b = next((o for o in clappers(s) if o.get("iid") == iid), None)
        st = control(b)[0]
        hp = int((s.get("hero") or {}).get("health") or 0)
        why = ("gone" if b is None else "hurt" if hp < hp0 else "time" if self._t - t0 > TIGHT_HOLD_S
               else None if st in ("Slam Antic", "Slam 0", "Slam 1") else f"B {st}")
        if why is None:
            return 0
        self.holds.append([iid, f0, f, why])
        self._hold = None
        return None

    def _tight_check(self, r: Run, k: int, s: dict, e: dict, cx: float, t: float) -> None:
        """TWO_TIGHT: another Clapper's slam began before A's Slam 0 + TIGHT_S0 (game frames): the way out over A to its
        far side when that fits (no side slash), else r.tight = (iid, 0) and the way as before."""
        ts0 = r.ta + r.ks0 / 60.0                             # A's Slam 0 on the clock
        if (t - ts0) * 60.0 > TIGHT_S0 + 8:
            return                                            # past the apex (a late tick): not decided here
        for o in clappers(s):
            if o.get("iid") == r.iid:
                continue
            st, tin = control(o)
            if st not in ("Slam Antic", "Slam 0", "Slam 1"):
                continue
            if (t - tin - ts0) * 60.0 >= TIGHT_S0:
                continue
            bx = float(o["pos"][0])
            away = 1 if cx > bx else -1                       # from B through A: A's far side
            room = (cx - WALL_L) if away < 0 else (WALL_R - cx)
            land = cx + away * min(TIGHT_LAND_U, room - self.cfg.wall_pad)
            if room >= TIGHT_DASH_ROOM and abs(land - bx) >= TWO_REACH_U:
                r.tight = (o.get("iid"), away)
                r.near, r.over_dir, r.side_why = 0, away, "tight"
            else:
                r.tight = (o.get("iid"), 0)
            return

    def _chain(self, r: Run, k: int, f: int, s: dict, e: dict, t: float, sim, hp: int) -> int | None:
        """TWO_AIRCHAIN (combat.air_chain) in A's way out: the plan's keys for frame f + 2, or None (the way out as
        before). The plan is searched when another Clapper is in Slam Antic, re-checked every tick, searched again
        when the check fails; the strike press hands the run over to B (a run on B in its 'after' phase)."""
        F = f + 2
        b = None
        if r.chain is not None:
            b = next((o for o in clappers(s) if o.get("iid") == r.chain.b_iid), None)
            if b is None or control(b)[0] not in ("Slam Antic", "Slam 0"):
                r.chain_log.append([f, "drop_b", r.chain.row()])
                r.chain, r.chain_off = None, "b gone"
                return None
        else:
            if F < r.chain_next or (s.get("hero") or {}).get("hero_accepting_input") is False:
                return None
            if on_ground(s):
                return None
            cands = [o for o in clappers(s) if o.get("iid") != r.iid and control(o)[0] == "Slam Antic"
                     and o.get("iid") not in self._closed]
            if not cands:
                return None
            hx = hero_x(s)
            b = min(cands, key=lambda o: abs(float(o["pos"][0]) - hx))
        ctx = self._chain_ctx(r, s, b, sim, f)
        t0 = time.perf_counter()
        if r.chain is None:
            plan = _ac.search(sim, ctx)
            if plan is None:
                r.chain_next = F + _ac.RESEARCH_F
                if not r.chain_log or r.chain_log[-1][1] != "none":
                    r.chain_log.append([f, "none", None, round(1e3 * (time.perf_counter() - t0), 1)])
                return None
            r.chain = plan
            r.chain_log.append([f, "plan", plan.row(), round(1e3 * (time.perf_counter() - t0), 1)])
        elif not _ac.check(sim, ctx, r.chain):
            plan = _ac.search(sim, ctx)
            if plan is None and r.chain.f_press - F <= _ac.KEEP_F:
                # no new plan this close to the strike: the committed one goes on (dropping it leaves her floating in
                # front of B's hammer with the planner)
                if not r.chain_log or r.chain_log[-1][1] != "keep":
                    r.chain_log.append([f, "keep", r.chain.row(), round(1e3 * (time.perf_counter() - t0), 1)])
                plan = r.chain
            elif plan is None:
                r.chain_log.append([f, "lost", r.chain.row(), round(1e3 * (time.perf_counter() - t0), 1)])
                r.chain, r.chain_off = None, "lost"
                return None
            if plan is not r.chain:
                if r.chain.pressed_down is not None:
                    plan.f_down, plan.pressed_down = r.chain.f_down, r.chain.pressed_down
                r.chain = plan
                r.chain_log.append([f, "replan", plan.row(), round(1e3 * (time.perf_counter() - t0), 1)])
        p = r.chain
        m = _ac.mask_at(p, F)
        if p.f_down is not None and p.pressed_down is None and m & M_A:
            p.pressed_down = F
        if p.pressed is None and F >= p.f_press and m & M_A:
            p.pressed = F
            r.chain_log.append([f, "strike", p.row()])
            # the strike: the run passes to B (its 'after' phase: the bounce, the way out, the landing)
            st_b, tin_b = control(b)
            ta_b = t - tin_b
            nb = Run(iid=b.get("iid"), fa=int(f - round(tin_b * 60.0)), face=1 if b.get("flipX") else -1, ta=ta_b,
                     phase="after", k_press=int(round((t - ta_b) * 60.0)) + SEND_AHEAD + self.cfg.lag, hp0=hp,
                     chain_from=r.iid)
            nb.k = nb.k_press
            nb.sent.append((F, m))
            self._close("done", "chain")
            self.run = nb
            return m
        r.sent.append((F, m))
        return m

    def _chain_ctx(self, r: Run, s: dict, b: dict, sim, f: int) -> "_ac.Ctx":
        """The air chain's view of this STATE: B (its centre, facing, antic frame at the start state's frame fo), A's
        body box (its collider, else BODY_FRONT / BACK), her x and facing."""
        a = next((o for o in clappers(s) if o.get("iid") == r.iid), None)
        a_box = None
        for col in (a or {}).get("colliders") or ():
            nm = str(col.get("name") or "")
            if (nm == CLAPPER or nm.startswith(CLAPPER + " (")) and col.get("enabled") and col.get("verts_world"):
                xs, ys = col["verts_world"][0::2], col["verts_world"][1::2]
                a_box = (float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys)))
                break
        if a is not None and a_box is None:
            ax, ay = float(a["pos"][0]), float(a["pos"][1])
            fa = 1 if a.get("flipX") else -1
            x0, x1 = sorted((ax + fa * BODY_FRONT, ax - fa * BODY_BACK))
            a_box = (x0, ay - 4.43, x1, ay - 0.53)
        h = s.get("hero") or {}
        fc = h.get("facing")
        tin = control(b)[1]
        return _ac.Ctx(b_iid=b.get("iid"), b_x=float(b["pos"][0]), b_y=float(b["pos"][1]),
                       b_face=1 if b.get("flipX") else -1, kb0=int(round(tin * 60.0)) - (f - sim.fo), a_box=a_box,
                       hero_x=hero_x(s), face=1 if fc is None or float(fc) >= 0 else -1, tls=_ac.timelines())

    # ---- SP13 SSBOT_FORUM_CLAWSTRIKE ----

    def _cs_cfg(self) -> "_cs.CsCfg":
        if self._csx is None:
            self._csx = _cs.ClawStrike(_cs.CsCfg.from_env())
        return self._csx.cfg

    def _cs_decline(self, r: Run, f: int, why: str) -> None:
        if not any(x[1] == "no" and x[2] == why for x in r.cs_log):
            r.cs_log.append([f, "no", why])
            self.cs_declines[why] = self.cs_declines.get(why, 0) + 1

    def _cs_other(self, s: dict, r: Run) -> dict | None:
        return next((o for o in clappers(s) if o.get("iid") != r.iid), None)

    @staticmethod
    def _cs_box(o: dict | None) -> tuple | None:
        """A Clapper's body AABB (its collider, else the standing box from BODY_FRONT / BACK)."""
        if o is None:
            return None
        for col in o.get("colliders") or ():
            nm = str(col.get("name") or "")
            if (nm == CLAPPER or nm.startswith(CLAPPER + " (")) and col.get("enabled") and col.get("verts_world"):
                xs, ys = col["verts_world"][0::2], col["verts_world"][1::2]
                return float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))
        ax, ay = float(o["pos"][0]), float(o["pos"][1])
        fa = 1 if o.get("flipX") else -1
        x0, x1 = sorted((ax + fa * BODY_FRONT, ax - fa * BODY_BACK))
        return x0, ay - 4.43, x1, ay - 0.53

    def _cs_ctx(self, r: Run, s: dict, e: dict, sim, t: float, f: int) -> "_cs.CsCtx":
        h = s.get("hero") or {}
        fc = h.get("facing")
        kb0 = int(round((t - r.ta) * 60.0)) - (f - sim.fo)        # S's antic frame at the sim's rollout index 0
        return _cs.CsCtx(s_iid=r.iid, s_x=float(e["pos"][0]), s_y=float(e["pos"][1]), s_face=r.face, kb0=kb0,
                         hero_x=hero_x(s), face=1 if fc is None or float(fc) >= 0 else -1,
                         other_box=self._cs_box(self._cs_other(s, r)), tls=_ac.timelines())

    def _cs_try(self, r: Run, k: int, f: int, s: dict, e: dict, ground: bool, accepting: bool, sim, hp: int,
                t: float, why: str) -> int | None:
        """SP13: start the Clawline approach on S when its gates hold and a plan exists (the keys for frame f + 2),
        else None (the playbook / the planner as before; the decline is logged once per reason)."""
        c = self._cs_cfg()
        if r.cs is not None or r.as_air or f + 2 < r.cs_next:
            return None
        if not _cs.CLAWSTRIKE:
            return self._as_try(r, k, f, s, e, ground, accepting, sim, hp, t, why)
        h = s.get("hero") or {}
        cx = float(e["pos"][0])
        hx = hero_x(s)
        x = (hx - cx) * r.face
        reason = None
        if not accepting:
            reason = "input"
        elif int(h.get("silk") or 0) < 1 or not ((h.get("can") or {}).get("harpoon", True)):
            reason = "silk"
        elif x <= 0:
            reason = "behind"
        elif k > c.k_last:
            reason = "late"
        else:
            o = self._cs_other(s, r)
            if o is not None:
                ob = self._cs_box(o)
                lo, hi = sorted((hx, cx))
                if ob[0] - _cs.HALF_W < hi and ob[2] + _cs.HALF_W > lo:
                    reason = "other in the way"
            if reason is None and o is not None and c.other_free and control(o)[0] not in ("Idle", "Walk"):
                # fp3 (b812a76, w13 force): 6 of 35 runs lost HP, all to the other one - its small runes in the hop / the
                # lock (3), a big rune (1), its body / hammer (2). S's antic holds it (Buddy Is Attacking: no new move),
                # so only a move under way at the start reaches her in the lock: none at all
                reason = f"other {control(o)[0]}"
            if reason is None and c.room:
                # only when she cannot leave the hammer's reach (13 u from its centre) on her side
                out_x = cx + r.face * 13.0
                if WALL_L + 0.5 <= out_x <= WALL_R - 0.5 and (
                        o is None or not min(hx, out_x) - 0.5 < float(o["pos"][0]) < max(hx, out_x) + 0.5):
                    reason = "room"
        if reason is None:
            if self._csx.params is None:
                self._csx.params, self._csx.terrain = sim.params, sim.terrain
            t0 = time.perf_counter()
            plan = self._csx.plan(sim, self._cs_ctx(r, s, e, sim, t, f), ground, accepting)
            ms = round(1e3 * (time.perf_counter() - t0), 1)
            if plan is None:
                r.cs_next = f + 2 + 2                          # a failed search is tried again 2 frames later
                if not any(x_[1] == "none" for x_ in r.cs_log):
                    r.cs_log.append([f, "none", k, ms])
                reason = "no plan"
        if reason is None and self._cs_bomb(r, plan, cx, hx):
            reason = "other bomb"                             # a small rune of the other one on the Clawline's path
        if reason is None and self._cs_circle(s, cx, hx, self._t):
            reason = "other rune circle"
        if reason is not None:
            self._cs_decline(r, f, reason)
            if _cs.AIRSTRIKE and reason in ("no plan", "silk", "other in the way", "room"):
                return self._as_try(r, k, f, s, e, ground, accepting, sim, hp, t, why)
            return None
        r.cs, r.cs_toward = plan, (1 if cx > hx else -1)
        r.phase, r.k_start, r.x_start, r.hp0, r.why = "cs_pre", k, round(x, 3), hp, ""
        hb = h.get("box") or [0, FLOOR_Y - 1.56, 0, 0]
        r.cs_log.append([f, "plan", why, k, round(x, 2), round(float(hb[1]) - (FLOOR_Y - 1.56), 2), plan.row(), ms])
        return self._cs_step(r, k, f, s, e, ground, accepting, sim, t)

    def _as_try(self, r: Run, k: int, f: int, s: dict, e: dict, ground: bool, accepting: bool, sim, hp: int,
                t: float, why: str) -> int | None:
        """SP13a SSBOT_FORUM_AIRSTRIKE: in the air at S's antic with no ground strike in time (and no Clawline plan):
        air_chain's search with S as its B; the keys for frame f + 2 or None."""
        if ground or not accepting or r.as_air or k > 40:
            return None
        h = s.get("hero") or {}
        fc = h.get("facing")
        a_entry = int(round(f - (t - r.ta) * 60.0))
        actx = _ac.Ctx(b_iid=r.iid, b_x=float(e["pos"][0]), b_y=float(e["pos"][1]), b_face=r.face,
                       kb0=sim.fo - a_entry, a_box=self._cs_box(self._cs_other(s, r)), hero_x=hero_x(s),
                       face=1 if fc is None or float(fc) >= 0 else -1, tls=_ac.timelines())
        t0 = time.perf_counter()
        plan = _ac.search(sim, actx)
        ms = round(1e3 * (time.perf_counter() - t0), 1)
        if plan is None:
            r.cs_next = f + 2 + _ac.RESEARCH_F
            if not any(x_[1] == "as_none" for x_ in r.cs_log):
                r.cs_log.append([f, "as_none", k, ms])
            self._cs_decline(r, f, "as no plan")
            return None
        hb = h.get("box") or [0, FLOOR_Y - 1.56, 0, 0]
        r.as_air, r.cs_strike = True, plan
        r.phase, r.k_start, r.hp0, r.why = "cs_strike", k, hp, ""
        r.cs_log.append([f, "as_plan", why, k, round((hero_x(s) - float(e["pos"][0])) * r.face, 2),
                         round(float(hb[1]) - (FLOOR_Y - 1.56), 2), plan.row(), ms])
        return self._cs_step(r, k, f, s, e, ground, accepting, sim, t)

    def _cs_bomb(self, r: Run, plan, cx: float, hx: float) -> bool:
        """SP13: a lit / forecast small-rune bomb of any Clapper (rune_bombs.frames from this STATE; Task 182 seq 310: S's own count too: a placed rune is
        no less a rune for belonging to the target; the decline's name stays "other bomb") meets her box on the Clawline's path: in place to the press + 10
        (the hop's box bottom), the dash to the stop (S's front - 2.1 u), held there to control, the bounce over the stop to the press + 50."""
        bk = self._bombs
        if bk is None or not len(bk):
            return False
        import numpy as np
        from ssbot.combat import rune_bombs as _rb
        own = {int(o) for o in bk[:, 0]}
        k0 = self._sg_k0(r)
        kp = int(plan.k_press)
        ks = np.arange(k0, kp + 51)
        d = 1.0 if cx > hx else -1.0
        x_stop = cx - d * (_cs.BODY_FRONT + 2.1 + _cs.HALF_W)
        x1 = hx + d * _cs.ANTIC_DX
        xs = np.where(ks <= kp + 10, hx, np.where(ks >= kp + 27, x_stop, x1 + (x_stop - x1) * (ks - kp - 10) / 17.0))
        bb = float(plan.bb_press or 1.0)
        hs = np.where(ks <= kp + 32, bb, bb + np.minimum(4.0, 0.29 * (ks - kp - 32)))
        ys = 3.0 + hs + 1.0394
        return bool(_rb.occupied(bk, xs, ys, ks - k0, SG_BOMB_M, own).any())

    def _cs_circle(self, s: dict, cx: float, hx: float, t: float) -> bool:
        """fp4 (162ca26): a big rune circle (lit, or its object still to burst: not seen lit then unlit, younger than
        1.6 s) over the Clawline's x span (her x to the stop 2.1 u short of S's front) - the other one Idle at the
        start, its circle burst in her lock (k 21)."""
        d = 1.0 if cx > hx else -1.0
        x_stop = cx - d * (_cs.BODY_FRONT + 2.1 + _cs.HALF_W)
        lo, hi = min(hx, x_stop) - 0.5, max(hx, x_stop) + 0.5
        self._life.update(self._f, s, t)
        return any(a < hi and b > lo for a, b in self._life.spans())

    @staticmethod
    def _cs_s_hit(s: dict, r: Run) -> bool:
        """A hit on S this tick that is not the Clawline's own (the strike's down slash)."""
        for ev in s.get("ev") or ():
            d = ev.get("d") or {}
            if (ev.get("k") == "hit" and d.get("type_key") == CLAPPER and (d.get("ent") or d.get("iid")) == r.iid
                    and "Harpoon" not in str(d.get("src") or "")):
                return True
        return False

    def _cs_step(self, r: Run, k: int, f: int, s: dict, e: dict, ground: bool, accepting: bool, sim,
                 t: float) -> int | None:
        """SP13: the Clawline approach's keys for frame f + 2 (the press, the lock to control, the strike), or None
        (the run aborted: the planner decides)."""
        F = f + 2
        p = r.cs
        h = s.get("hero") or {}
        if r.phase == "cs_pre":
            if F < p.f_press - 1 and sim is not None:
                # re-checked from this tick's state: the committed press, else another press (no new hop)
                ctx = self._cs_ctx(r, s, e, sim, t, f)
                hu = p.f0 + p.hop if p.hop else None
                q = self._csx.plan(sim, ctx, False, accepting, hop_until=hu, p_only=p.f_press)
                if q is None:
                    q = self._csx.plan(sim, ctx, False, accepting, hop_until=hu)
                    if q is None and p.f_press - F <= CS_KEEP_F:
                        # fp4: one plan lost 4 frames before its press - the abort left her in the hop in front of
                        # the hammer (Slam Collider 1 at k 54): the committed press goes on
                        if not any(x_[1] == "keep" for x_ in r.cs_log):
                            r.cs_log.append([f, "keep", k])
                        q = p
                    elif q is None:
                        r.cs_log.append([f, "lost", k])
                        self._close("abort", "cs lost")
                        return None
                    else:
                        r.cs_log.append([f, "replan", k, q.row()])
                if q is not p:
                    q.f0, q.hop = p.f0, p.hop                  # the hop's own frames
                    r.cs = p = q
            m = _cs.plan_mask(p, F, r.cs_toward)
            if F >= p.f_press + 1:
                r.phase = "cs_lock"
                r.cs_k_press = k - (F - p.f_press)
                r.cs_log.append([f, "press", r.cs_k_press])
            r.sent.append((F, m))
            return m
        if r.phase == "cs_lock":
            harp = str((h.get("anim") or {}).get("clip") or "").startswith("Harpoon")
            if accepting and not harp and F > p.f_press + 12:
                r.phase = "cs_strike"
                r.cs_k_ctrl = k - SEND_AHEAD
                hb = h.get("box") or [0, FLOOR_Y - 1.56, 0, 0]
                r.cs_log.append([f, "ctrl", r.cs_k_ctrl, round((hero_x(s) - float(e["pos"][0])) * r.face, 2),
                                 round(float(hb[1]) - (FLOOR_Y - 1.56), 2), round(float((h.get("vel") or [0, 0])[1]), 1)])
            elif F > p.f_press + 45:
                r.cs_log.append([f, "noctrl", k])
                self._close("abort", "cs no control")
                return None
            else:
                r.sent.append((F, 0))
                return 0
        # cs_strike: the down slash on S's Slam 0 body (air_chain's plans from this tick's hero model)
        if sim is None:
            self._close("abort", "cs no sim")
            return None
        cx = float(e["pos"][0])
        a_entry = int(round(f - (t - r.ta) * 60.0))                # S's antic entry as a STATE frame
        fc = h.get("facing")
        actx = _ac.Ctx(b_iid=r.iid, b_x=cx, b_y=float(e["pos"][1]), b_face=r.face, kb0=sim.fo - a_entry,
                       a_box=self._cs_box(self._cs_other(s, r)), hero_x=hero_x(s),
                       face=1 if fc is None or float(fc) >= 0 else -1, tls=_ac.timelines())
        cfg = self._cs_cfg()
        sp_ = r.cs_strike
        if r.as_air and sp_ is not None and not _ac.check(sim, actx, sp_):
            # SP13a: the air approach searched again (air_chain's grid: drift, down slash, umbrella, the strike)
            q = _ac.search(sim, actx)
            if q is not None:
                if sp_.pressed_down is not None:
                    q.f_down, q.pressed_down = sp_.f_down, sp_.pressed_down
                r.cs_log.append([f, "restrike", q.row(), q.n_ok])
                r.cs_strike = sp_ = q
            elif sp_.f_press - F <= _ac.KEEP_F:
                if not r.cs_log or r.cs_log[-1][1] != "keep":
                    r.cs_log.append([f, "keep", sp_.row()])
            else:
                r.cs_log.append([f, "nostrike", k])
                self._close("abort", "as no strike")
                return None
        elif sp_ is None or not _ac.check(sim, actx, sp_):
            f_min = max(F, a_entry + r.cs_k_ctrl + cfg.cd_f - 1, a_entry + cfg.press_k[0])
            plans = []
            for fp in range(f_min, a_entry + cfg.press_k[1] + 1):
                for d in cfg.drifts:
                    for dk in ((0,) if d == 0 else (r.cs_toward, -r.cs_toward)):
                        m_ = 0 if dk == 0 else (M_R if dk > 0 else M_L)
                        plans.append(_ac.Plan(F, m_, F + d, None, None, fp, fp - a_entry, r.iid))
            ok = _ac.evaluate(sim, actx, plans, F) if plans else []
            if ok:
                ok.sort(key=lambda q_: (abs(q_.k_press - 47), q_.d_end - q_.f0, q_.c_strike - q_.f_press))
                q = ok[0]
                q.n_ok = len(ok)
                r.cs_log.append([f, "strike" if sp_ is None else "restrike", q.row(), len(ok)])
                r.cs_strike = sp_ = q
            elif sp_ is not None and sp_.f_press - F <= _ac.KEEP_F:
                if not r.cs_log or r.cs_log[-1][1] != "keep":
                    r.cs_log.append([f, "keep", sp_.row()])
            else:
                kp = max(self.cfg.k_press, r.cs_k_ctrl + cfg.cd_f + 1)
                if kp > self.cfg.k_press_max_late + 2:
                    r.cs_log.append([f, "nostrike", k])
                    self._close("abort", "cs no strike")
                    return None
                # fp4 (162ca26): 3 of 41 runs had no strike plan at control (her stop 1.9-4.2 u in front of S) and the
                # abort left her in front of its hammer (Slam Collider 1, k 53-55): the playbook's press, open loop
                r.cs_log.append([f, "open", k, kp])
                r.phase, r.k_press_plan = "air", kp
                m = self._press_part(r, k, 0)
                if m is None:
                    return None
                r.sent.append((F, m))
                return m
        m = _ac.mask_at(sp_, F)
        if sp_.f_down is not None and sp_.pressed_down is None and m & M_A:
            sp_.pressed_down = F
        elif sp_.pressed is None and F >= sp_.f_press and m & M_A:
            sp_.pressed = F
            r.k_press = k
            r.phase = "after"
            r.cs_log.append([f, "pressed", k])
        r.sent.append((F, m))
        return m

    # ---- parts ----

    def _over_dir(self, cx: float, face: int) -> int:
        """The way out after the bounce: behind it (-face) with OVER_ROOM to the wall there, else in front (+face)
        with the room, else 0."""
        room = (lambda d: (cx - WALL_L) if d < 0 else (WALL_R - cx))
        for d in (-face, face):
            if room(d) >= self.cfg.over_room:
                return d
        return 0

    def _side_pref(self, r: Run, s: dict, e: dict, cx: float) -> tuple[int, str]:
        """SP5 SIDE: the world direction from its centre the hero should end on (+1 right), and why: the side toward the
        nearest other Clapper (two: end between them), else toward the nearer wall (one: between it and the wall);
        a tie keeps her side (in front). cfg.side_force (probes): +1 keep, -1 switch."""
        if self.cfg.side_force:
            return r.face * (1 if self.cfg.side_force > 0 else -1), "force"
        if self.side_hint and e.get("iid") in self.side_hint:
            return int(self.side_hint[e.get("iid")]), "pushmid"      # SP11b TWO_PUSHMID: F's wall side
        others = [float(o["pos"][0]) for o in s.get("ents") or ()
                  if o.get("type_key") == CLAPPER and not o.get("is_dead") and (o.get("hp") or 0) > 0 and o.get("pos")
                  and o.get("iid") != e.get("iid")]
        if others:
            ox = min(others, key=lambda x: abs(x - cx))
            if ox != cx:
                d = 1 if ox > cx else -1
                if TWO_SIDE:
                    # SP7: the other one free (it may start a slam the moment this one's Slam 1 ends: its hammer ~10
                    # frames after her landing) and its reach covering the landing between them: land on the far side,
                    # NEAR's 3.7 u when that is out of its reach, else SP1's dash way out (6.6-9.5 u from this one)
                    o = min((o for o in clappers(s) if o.get("iid") != e.get("iid")),
                            key=lambda o: abs(float(o["pos"][0]) - cx))
                    sep = abs(ox - cx)
                    if control(o)[0] in TWO_FREE_ST and sep - self.cfg.near_u_front < TWO_REACH_U:
                        return -d, ("two-away" if sep + self.cfg.near_u_behind >= TWO_REACH_U else "two-far")
                return d, "two"
        dl, dr = cx - WALL_L, WALL_R - cx
        if dl == dr:
            return r.face, "wall"
        return (-1 if dl < dr else 1), "wall"

    def _side_old(self, r: Run, s: dict, e: dict, cx: float) -> int:
        """SIDE with SP1's way out (the dash; NEAR off): the preferred side when the wall there leaves OVER_ROOM from its
        centre, else the other, else none."""
        pref, why = self._side_pref(r, s, e, cx)
        room = (lambda d: (cx - WALL_L) if d < 0 else (WALL_R - cx))
        for d, w in ((pref, why), (-pref, "room")):
            if room(d) >= self.cfg.over_room:
                r.side_why = w
                return d
        r.side_why = "room"
        return 0

    def _near_fit(self, d: int, cx: float, u: float) -> float | None:
        """The landing distance on world side d (u, from u down to near_u_min) whose spot fits inside the walls."""
        c = self.cfg
        room = ((cx - WALL_L) if d < 0 else (WALL_R - cx)) - c.wall_pad
        if room >= u:
            return u
        return room if room >= c.near_u_min else None

    def _near(self, r: Run, k: int, f: int, s: dict, e: dict, cx: float) -> int:
        """SP5 NEAR: the way out's keys for frame f + 2 (antic frame k) after the bounce, 0 = none."""
        c = self.cfg
        ks0 = k - r.ks0
        h = s.get("hero") or {}
        if r.near is None:
            if ks0 < c.near_decide_s0:
                return 0
            # off: behind first (SP1's way out), in front when that does not fit
            pref, why = self._side_pref(r, s, e, cx) if SIDE else (-r.face, "behind")
            if why == "two-far":
                # SP7 TWO_SIDE: SP1's dash way out on that side (kept: the other one may be in its antic by Slam 0 + 20)
                room = (lambda d: (cx - WALL_L) if d < 0 else (WALL_R - cx))
                r.near, r.side_why = 0, why
                ds = [d for d in (pref, -pref) if room(d) >= c.over_room]
                if self._guard is not None and len(ds) > 1 and self._guarded_spot(r, cx + ds[0] * TIGHT_LAND_U):
                    if not self._guarded_spot(r, cx + ds[1] * TIGHT_LAND_U):
                        ds, r.side_why = ds[::-1], "guard"     # SP11-0: away from the other one's danger
                r.over_dir = ds[0] if ds else 0
                return 0
            x_rel = (hero_x(s) - cx) * r.face
            fits = {}
            for d in (pref, -pref):
                u = self._near_fit(d, cx, c.near_u_front if d == r.face else c.near_u_behind)
                # behind: past its back by near_cross_s0 at NEAR_V from the key's start (else she comes down on it).
                # SP6 EARLY: the measured speed (0.138 u / frame in all 104 behind way-outs of SP5 t1-t3 and SP6 t1, not
                # NEAR_V) and early_cross_u: the early hits push it 0.36-0.48 u, the strike lands farther out, and
                # the two t1 failures (its Idle turn into her at Slam 0 + 43-44) started the way at 1.99 / 2.09 u
                v, cu = (c.early_near_v, c.early_cross_u) if EARLY else (NEAR_V, c.near_cross_u)
                clear = d == r.face or (x_rel - v * (c.near_cross_s0 - max(ks0, c.near_s0_behind)) <= -cu)
                fits[d] = (u, u is not None and clear)
            r.near = next((d for d in (pref, -pref) if fits[d][1]), 0)
            g_switch = False
            if self._guard is not None and r.near != 0 and self._guarded_spot(r, cx + r.near * fits[r.near][0]):
                # SP11-0 TWO_GUARD: the landing spot in the other one's danger span (its jump landing band, its big rune
                # circle): the other side when that fits and is clear of them
                o = -r.near
                if fits[o][1] and not self._guarded_spot(r, cx + o * fits[o][0]):
                    r.near, g_switch = o, True
            if r.near == 0:
                r.side_why = "old"
                return 0
            r.near_u = fits[r.near][0]
            r.side_why = "guard" if g_switch else (
                why if r.near == pref else ("room" if fits[pref][0] is None else "clear"))
        d = r.near
        if ks0 < (c.near_s0_behind if d == -r.face else c.near_s0_front) or r.k_slash is not None:
            return 0
        # her x at the mask's frame (the keys in flight: this script's own masks, else her velocity)
        xw = hero_x(s)
        vx = float((h.get("vel") or [0, 0])[0])
        for fr in range(f + 1, f + SEND_AHEAD + c.lag):
            m0 = next((m for f2, m in reversed(r.sent) if f2 <= fr), None) if r.sent else None
            xw += vx / 60.0 if m0 is None else ((1 if m0 & M_R else 0) - (1 if m0 & M_L else 0)) * NEAR_V
        rel = (xw - cx) * r.face                                   # + in front
        y = float((h.get("pos") or [0.0, FLOOR_Y])[1]) - FLOOR_Y
        vy = float((h.get("vel") or [0.0, 0.0])[1])
        for _ in range(SEND_AHEAD + c.lag + 1):                    # y at the mask's frame + 1 (the slash's first frame)
            y += vy / 60.0
            vy -= GRAV / 60.0
        low = y <= c.slash_y
        if TWO_HANDOFF and TWO_PLAY and d == r.face:
            u0 = r.near_u
            self._ho_aim(r, s, cx, d)
            if r.near_u > u0 + 0.05 and r.k_turn is not None:
                # B's antic began after her turn (fixed point t2, 25266b4: two hand-offs landed 8.2 u in front of B,
                # A to B 11.9 / 12.1 u, B's antic at A0 + 33 / 37): on to its stand, the turn again there
                r.k_turn = None
        if r.k_turn is None:
            tx = cx + d * r.near_u
            reached = (xw - tx) * d >= 0.5 * NEAR_V                # the turn key moves her NEAR_V back to tx
            past = d == r.face or rel <= -c.near_cross_u
            if reached or (low and past and r.side_why != "ho_aim" and self._in_reach(e, cx, r.face, xw, -d)):
                r.k_turn = k
                return M_R if -d > 0 else M_L                      # the turn: she faces it
            return M_R if d > 0 else M_L
        if k > r.k_turn and k >= r.k_press + c.slash_cd and low and self._in_reach(e, cx, r.face, xw, -d):
            # the key toward it with the press: a protected touch of the hammer during the bounce (Recoil Twirl, about
            # half the strikes) locks her facing until the attack, which takes the direction held on its frame (SP5
            # t1: 4 of 34 front slashes went the other way after the turn key alone)
            r.k_slash = k
            return M_A | (M_R if -d > 0 else M_L)
        return 0

    @staticmethod
    def _in_reach(e: dict, cx: float, face: int, xw: float, look: int) -> bool:
        """The side slash from x xw facing look (+1 right) meets the Clapper's body box (its collider's x span when the
        STATE has it, else BODY_FRONT / BODY_BACK from its centre), with 0.1 u to spare."""
        span = None
        for col in e.get("colliders") or ():
            nm = str(col.get("name") or "")
            if ((nm == CLAPPER or (REACH_NAME and nm.startswith(CLAPPER + " ("))) and col.get("enabled")
                    and col.get("verts_world")):
                xs = col["verts_world"][0::2]
                span = (float(min(xs)), float(max(xs)))
                break
        if span is None:
            a, b = cx + face * BODY_FRONT, cx - face * BODY_BACK
            span = (min(a, b), max(a, b))
        lo, hi = (xw + SLASH_X[0], xw + SLASH_X[1]) if look > 0 else (xw - SLASH_X[1], xw - SLASH_X[0])
        return lo < span[1] - 0.1 and hi > span[0] + 0.1

    def _press_part(self, r: Run, k: int, m: int) -> int | None:
        c = self.cfg
        kp = r.k_press_plan if r.k_press_plan is not None else c.k_press
        if r.k_press is None:
            late = r.s0 is not None and k >= kp - 3
            if k >= kp or late:
                if r.s0 is not None and k - r.ks0 > c.press_late_max:
                    # Slam 0 seen and the frame is already past its window: the hammer comes before the slash
                    self._close("abort", "press window missed")
                    return None
                r.k_press = k
                r.phase = "after"
                return m | M_D | M_A
            if k >= kp - (c.k_press - c.k_down):
                m |= M_D
        return m

    def _x_at_mask(self, s: dict, f: int) -> float:
        """Her box centre's world x at the mask's frame f + 2 + lag: the STATE's x plus the frames already in flight
        (this script's own masks, else her velocity)."""
        c = self.cfg
        h = s.get("hero") or {}
        vx = float((h.get("vel") or [0, 0])[0])
        r = self.run
        xw = hero_x(s)
        for fr in range(f + 1, f + SEND_AHEAD + c.lag):
            m = next((m for f2, m in reversed(r.sent) if f2 <= fr), None) if r is not None and r.sent else None
            xw += vx / 60.0 if m is None else ((1 if m & M_R else 0) - (1 if m & M_L else 0)) * WALK_U
        return xw

    def _walk(self, s: dict, cx: float, face: int, f: int, band: tuple | None = None) -> int:
        """The walk mask for frame f + 2 + lag: where she stands before it (the STATE's x plus the frames already in
        flight: this script's own masks, else her velocity), none when that is inside STAND (or band), else one step
        toward its middle (she stops dead; STAND is wider than a step: no back and forth)."""
        c = self.cfg
        r = self.run
        lo, hi = band if band is not None else (r.stand if r is not None and r.stand else c.stand)
        xw = self._x_at_mask(s, f)
        x = (xw - cx) * face
        if lo <= x <= hi:
            return 0
        tx = cx + face * 0.5 * (lo + hi)
        return M_R if tx > xw else M_L

    def _early(self, r: Run, k: int, f: int, s: dict, e: dict, cx: float, ground: bool, m_walk: int) -> int:
        """SP6 EARLY: the mask for antic frame k in the walk phase - the side slash toward it when the attack is ready
        and its reach meets the body (the key toward it the frame before, the press held two frames with it: one
        rising edge, the direction toward it whichever of them the game takes), else the walk into EARLY_STAND while
        another early press can still come by early_k_max (no key away from it within early_quiet frames of a
        press), else m_walk (the walk into STAND)."""
        c = self.cfg
        toward = M_R if -r.face > 0 else M_L
        away = M_L if toward == M_R else M_R
        last = r.k_early[-1] if r.k_early else None
        if last is not None and k == last + 1:
            return M_A | toward                    # the press's second frame
        if last is not None and not r.stand:
            # after an early press the walk into early_post_stand: a hit's recoil (~0.5 u over 8 frames, on into the
            # jump when it came after antic frame ~18) and its knock-back (0.48 u) put her ~0.9 u farther at the
            # press (t2, ba5502e: x at the press 5.66-5.86 u after hits at 15-22 vs 4.86 without; the one hammer
            # hit pressed from 5.78 u at Slam 0 - 1)
            m_walk = self._walk(s, cx, r.face, f, band=c.early_post_stand)
        quiet = last is not None and k - last <= c.early_quiet
        if not ground or k > c.early_k_max:
            return 0 if quiet and m_walk & away else m_walk
        nxt = k if last is None else max(k, last + c.early_cd)
        if r.k_start is not None:
            # the frame before the press is ours and carries the key toward it (t1, 1cec5f0: a walk away sent before
            # the press landed with it - the slash went the other way, 0 of 14 presses at the script's 2nd frame hit)
            nxt = max(nxt, r.k_start + 2)
        cd = ((s.get("hero") or {}).get("tm") or {}).get("atk_cd")
        if cd is not None:
            # the STATE's cooldown after frame f's update; the mask's frame checks it after one more decrement
            left = float(cd) * 60.0 - (SEND_AHEAD + c.lag - 1)
            if left > 0.05:
                nxt = max(nxt, k + int(left + 0.95))
        if nxt > c.early_k_max:
            return 0 if quiet and m_walk & away else m_walk
        xw = self._x_at_mask(s, f)
        xr = (xw - cx) * r.face
        band = c.early_stand
        lo_x, hi_x = c.early_min_u, 99.0                 # the press's x window (u in front, centre to centre)
        if nxt >= c.early_late_k:
            # a late press (its hit's recoil runs on into the jump): from early_late_u at most (t2 / t3: the two hammer
            # hits pressed the strike from 5.66-5.78 u at Slam 0 - 1 after an early hit at antic frame 22 from
            # 4.6-4.7 u; hits from <= 4.5 u put her at <= 5.56 u) and early_late_lo at least (t4, 0db621e: two presses
            # at 23 from 3.98-4.12 u left her at 3.81-3.96 u at the jump, below BAND's 4.0)
            lo_x, hi_x = c.early_late_lo, c.early_late_u + 0.05
            band = (c.early_late_lo + 0.1, c.early_late_u + 0.05)
        ok = lambda x_rel, x_w: lo_x <= x_rel <= hi_x and self._in_reach(e, cx, r.face, x_w, -r.face)   # noqa: E731
        prev = r.sent[-1][1] if r.sent else 0
        fc = (s.get("hero") or {}).get("facing")
        facing = prev & toward or (not prev & away and fc is not None and float(fc) * -r.face > 0)
        if k >= nxt and ok(xr, xw) and facing and not prev & away:
            r.k_early.append(k)
            return M_A | toward
        if nxt - k <= 1 and not facing and ok(xr - WALK_U, xw - r.face * WALK_U):
            return toward                           # the frame before the press: toward it (she turns to it)
        # the walk into the band: toward it only down to the window (abc block of the A/B, 74174bd: the frame-before
        # toward key repeated while a late press stayed out of its window walked her from 4.25 to 3.31-3.42 u: no
        # strike, three hammer hits); away from it only when no press is due within early_quiet frames
        m = self._walk(s, cx, r.face, f, band=band)
        if m & toward and xr - WALK_U < lo_x:
            m = 0
        if m & away and (quiet or (nxt - k <= c.early_quiet and lo_x <= xr <= hi_x)):
            return 0                                # no key away from it around a press
        return m

    def _try_start(self, r: Run, k: int, s: dict, e: dict, ground: bool, accepting: bool, hp: int, f: int
                   ) -> int | None:
        c = self.cfg
        lim = c.k_start_max
        if r.k_air is not None or r.late:
            lim = c.k_jump_late2 if LATE else c.k_jump_late - 1
        if k > lim:
            if not r.why:
                r.why = "late"
            r.phase = "abort"
            self._close("abort", r.why)
            return None
        cx = float(e["pos"][0])
        x = (hero_x(s) - cx) * r.face
        h = s.get("hero") or {}
        vx = float((h.get("vel") or [0, 0])[0])
        if not accepting:
            r.why = "no input (sprint, recoil)"
            r.late = r.late or LATE                       # SSBOT_FORUM_SLAM_PLAY_LATE: start when input returns
            return None
        if x <= 0:
            r.why = "behind"
            return None
        if not c.reach[0] <= x <= c.reach[1]:
            r.why = f"distance {x:.1f}"
            return None
        lo, hi = c.stand
        tgt = min(max(x, lo), hi)
        tx = cx + r.face * tgt
        if not WALL_L + c.wall_room <= tx <= WALL_R - c.wall_room:
            dmax = ((WALL_R - c.wall_room) - cx) if r.face > 0 else (cx - (WALL_L + c.wall_room))
            if not (_jb.ENABLED and dmax >= NEAR_STAND_U):
                r.why = "wall"
                return None
            # SSBOT_FORUM_JUMP_BEHIND: between it and a wall after a jump: a nearer stand point (module constants)
            r.stand, r.band = (NEAR_STAND_U, min(dmax, hi)), (NEAR_BAND_LO, c.band[1])
            lo, hi = r.stand
            tgt = min(max(x, lo), hi)
        if not ground:
            if c.air and r.k_air is None and (k <= c.k_air_max or (LATE and r.late)):
                # in the air at the antic (a hop): steer toward STAND (never the jump), start once she lands
                r.phase, r.k_air, r.hp0, r.why = "land", k, hp, ""
                return self._walk(s, cx, r.face, f)
            r.why = "in the air"
            return None
        need = abs(tgt - x) / WALK_U + abs(vx) / 8.25 * 2 + 1
        band = r.band or c.band
        late_ok = (r.k_air is not None or r.late) and band[0] <= x <= band[1]   # landed late inside the jump band
        if LATE and (r.k_air is not None or r.late) and not late_ok:
            # LATE: a late start walks into the jump band (the walk phase) when that fits by K_JUMP_LATE2
            gap = max(x - (band[1] - 0.1), (band[0] + 0.1) - x, 0.0)
            late_ok = k + gap / WALK_U + abs(vx) / 8.25 * 2 + 1 <= c.k_jump_late2
        if k + need > c.k_jump - 1 and not late_ok:
            r.why = "no time to walk"
            return None
        r.phase, r.k_start, r.x_start, r.hp0, r.why = "walk", k, round(x, 3), hp, ""
        return self._walk(s, cx, r.face, f)
