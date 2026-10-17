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
from dataclasses import dataclass, field

from ssbot.combat import jump_behind as _jb
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


class SlamPlay:
    def __init__(self, cfg: PlayCfg | None = None):
        self.cfg = cfg or PlayCfg.from_env()
        self.run: Run | None = None
        self.done: list[Run] = []            # finished runs of this episode (the stats)
        self._closed_iid = None              # the Clapper whose slam was handled: no second look until it leaves it
        self._closed: set = set()            # TWO_PLAY: every Clapper whose slam was handled (until it leaves it)
        self._jfam: dict = {}                # TWO_PLAY: Clapper iid -> "j" / "jc" (its jump move) / "jc_landed"
        self._rune: dict = {}                # TWO_PLAY: Clapper iid -> (landing x, facing, game time) of a jump cast

    def reset(self) -> None:
        self.run = None
        self.done = []
        self._closed_iid = None
        self._closed, self._jfam, self._rune = set(), {}, {}

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

    def _two_danger(self, s: dict, e: dict, tx: float, t: float) -> str | None:
        """TWO_PLAY: why the other Clapper can reach the stand point tx during the strike (module constants), or None."""
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
            if rc is not None and t <= rc[2] + TWO_RUNE[2] and TWO_RUNE[0] <= (tx - rc[0]) * rc[1] <= TWO_RUNE[1]:
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
        return dict(out)

    def active(self) -> bool:
        return self.run is not None and self.run.phase in ("land", "walk", "jump", "air", "after")

    def abort(self, why: str) -> None:
        """Hand the slam back to the planner (the supervisor took the keys)."""
        if self.active():
            self._close("abort", why)
        elif self.run is not None and self.run.phase == "wait":
            self.run.why = why

    def _close(self, phase: str, why: str = "") -> None:
        r = self.run
        if r is not None:
            if r.phase in ("walk", "jump", "air", "after") or phase == "abort":
                r.phase = phase
            r.why = r.why or why
            self.done.append(r)
            self._closed_iid = r.iid
            if TWO_PLAY:
                self._closed.add(r.iid)
        self.run = None

    def step(self, f: int, s: dict, ground: bool, accepting: bool = True, t_game: float | None = None,
             skip: frozenset | None = None) -> int | None:
        """The mask for frame f + 2 from the STATE of frame f, or None (the planner decides).

        t_game: the game clock (s; the backend's Stamp.t_game_s, the sum of the scaled dt: it stands still through
        hit-stop freezes and pauses). The script's frames k count game frames from the antic entry (its Control state
        time): a freeze in the slam (SP2: a hit that takes the Clapper across 80 / 50 / 20 HP freezes the game for
        ~12 frames) no longer moves the jump and the press ahead of the Clapper. None: the STATE frame f is the clock
        (the frame count of SP1)."""
        c = self.cfg
        t = f / 60.0 if t_game is None else float(t_game)
        e = self._two_pick(s, t) if TWO_PLAY else clapper(s)
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
        if st not in SLAM_STATES or (e is not None and e.get("iid") != self._closed_iid):
            self._closed_iid = None
        if r is None:
            if st != "Slam Antic" or (e is not None and e.get("iid") == self._closed_iid):
                return None
            face = 1 if e.get("flipX") else -1
            r = self.run = Run(iid=e.get("iid"), fa=int(f - round(tin * 60.0)), face=face, ta=ta)
        if r.phase in ("done", "abort"):
            return None
        h = s.get("hero") or {}
        hp = int(h.get("health") or 0)
        if st == "Slam 0" and r.s0 is None:
            r.s0 = f
            r.ks0 = int(round(((t if t_game is None else t - tin) - r.ta) * 60.0))
        k = int(round((t - r.ta) * 60.0)) + SEND_AHEAD + c.lag     # the antic frame this tick's mask lands on
        r.k = k
        if r.hp0 is not None and hp < r.hp0:
            self._close("abort", "hurt")
            return None
        if r.phase == "land" and ground:
            r.phase = "wait"                              # landed: the start check (walk time from here)
        if r.phase == "land":
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
            if TWO_PLAY:
                # SP7: not while the other Clapper can reach the stand point during the strike (the planner decides)
                cx0 = float(e["pos"][0])
                x0 = (hero_x(s) - cx0) * r.face
                tx = cx0 + r.face * min(max(x0, c.stand[0]), c.stand[1])
                why = self._two_danger(s, e, tx, t)
                if why is not None:
                    r.why = why
                    return None
            m = self._try_start(r, k, s, e, ground, accepting, hp, f)
            if m is None:
                return None
            if EARLY and k < c.k_jump and r.phase == "walk":
                m = self._early(r, k, f, s, e, float(e["pos"][0]), ground, m)   # SP6: no key away before a press
            if k < c.k_jump:
                r.sent.append((f + SEND_AHEAD, m))
                return m
            # a late landing inside the jump band: the jump this tick (below)
        cx = float(e["pos"][0])
        x = (hero_x(s) - cx) * r.face                     # in front: > 0
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
                if float((h.get("vel") or [0, 0])[1]) > 6.0:
                    r.bounced = True
                elif k > r.k_press + 14:
                    self._close("abort", "no bounce")
                    return None
            if ground and k > r.k_press + 8:
                self._close("done", "landed")
                return None
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
                r.over_dir = next((d for d in (pref, -pref) if room(d) >= c.over_room), 0)
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
            if r.near == 0:
                r.side_why = "old"
                return 0
            r.near_u = fits[r.near][0]
            r.side_why = why if r.near == pref else ("room" if fits[pref][0] is None else "clear")
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
        if r.k_turn is None:
            tx = cx + d * r.near_u
            reached = (xw - tx) * d >= 0.5 * NEAR_V                # the turn key moves her NEAR_V back to tx
            past = d == r.face or rel <= -c.near_cross_u
            if reached or (low and past and self._in_reach(e, cx, r.face, xw, -d)):
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
            if col.get("name") == CLAPPER and col.get("enabled") and col.get("verts_world"):
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
