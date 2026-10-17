"""The Wanderer dash slash (DashStab) in the jump cast's antic (task 1v1 SP6, the person 2026-10-16: "if she is too far
to slash during the big rune's antic, try the dash slash"; forum.md 70), and SP8's two answers to "the two jump moves
mostly start their antic far away; try either dash slash x2 or dash then stop and side slash x2" (forum.md 72).

SSBOT_FORUM_JB_DASH_SLASH=1 (read by train.forum_planner_policy; since the SP8a A/B on with SSBOT_FORUM_V2, =0 off):
when the Clapper (Song Heavy Sentry) enters the jump cast's antic (Control "Cast Slam Antic", 16 frames, then "Cast
Slam Antic 2", 40 frames, Jump Aim at +55/56; SP4 / SP5 A/B: the hero 9.2 u from its centre at the antic start (p10 /
90 6.2 / 10.3), 0.25 hits per antic) and the hero stands on the ground in front of it beyond the side slash's reach,
the bot plays the dash slash as a script: the ground dash toward it with the dash key HELD (the sprint FSM's Dashed
state goes to the sprint only while the dash is held, and Ground Sprint skids out when it is released; t3, 79eb963: a
2-frame dash ran on as Dash To Run and the attack was a plain slash, 8 of 8), the attack pressed on the dash's last
frames (Ground Sprint reads it queued, 0.1 s: the stab starts on the first sprint frame), the dash key and the key
toward it held until the stab hits, then no key through the recoil until her control returns; the planner decides again
after that (or at once, all keys released, when the stab is not seen to hit).

The model (C:\\ssbot\\data\\m2_dash_slash: the decompiled hornet_sprint FSM, the person's 92 Wanderer dash slashes;
`stab_path`; SP8 calibrated on SP6 t6's 9 live stabs, C:\\ssbot\\data\\m2_dash_slash\\combo\\model_calib_bot.txt): the
dash 28 u/s on frames 1-7 after the dash's mask (3.27 u; live 3.36); the stab's clip from frame 8, vx 26.9 for 5 frames
then 17.5; its collider (0 .. 3.10 u in front of her transform, the side slash's reach) active from 7 to 14 frames
after the stab starts (live: hits at frame 15-16 after the dash's mask; SP6's model put them one frame early); its body
front in the cast antic 1.873 u from its centre (SP6 used the Idle box's 2.25: the audit's recorded collider,
antic_audit); on a hit she lunges on 2 frames at 17.5 u/s (SP8 t2: 0.6 u; the hit may also register a frame late), then
the recoil: vx 30 u/s away, vy +20, x0.85 per frame for 20 frames (0.333 s: ~3.2 u back, ~2.1 u up), control back
0.344-0.48 s after the press, then the fall at 60 u/s^2 (1.2 u/s per 50 Hz physics step; kinematics.py; SP6 used 72).
An enemy in an antic cannot block (the person; the Clapper has no guard), so only the hit branch is modelled: the start
needs the predicted hit, her box front never nearer than its body front + STAB_MARGIN during the lunge, and her landing
by the Jump Aim (+55) minus LAND_MARGIN frames. A miss (the stab not seen to hit by the window's end) lunges ~4.4 u on
and hands back to the planner.

SSBOT_FORUM_JB_DASH_COMBO=1 (SP8 T1, follows v2 like JB_DASH_SLASH, only with it;
C:\\ssbot\\data\\m2_dash_slash\\combo\\answer.txt section 4): after the DashStab's hit the Wanderer RecoilStab (RS: a
hover, then a lunge 45 u/s forward and 15 down) - a NEW attack press after the hit (holding it from the stab never
triggers it), read from W Recoil Cancelable (the earliest RS start g15 game frames after the hit): no key from the hit
to the press, the attack on g16-17 (the mask's game frame; held 2 frames: one rising edge), then no key - no dash (an
air dash would cancel it), no jump, no direction - until the RS hits (src RecoilStab, ~g24-26) or its clip ends. Only
when the dash starts >= combo_d_min (10.0 u: the RS hit 0.67 u outside its body at the latest collider frame) and the
RS hit is predicted by antic frame rs_k_max (52; the Jump Aim at 55): this replaces the stab's landing rule (with the
RS she lands ~aim + 33). The RS bounces her (vy -10, then +17.4; no i-frames; the air dash refreshed): no key until the
Jump Aim + post_aim_f (its body rises in place: 0.85 u above the floor at the aim, 2.93 at +3, 5.72 at +9), then the
planner (JUMP_BEHIND). The game clock (Stamp.t_game_s) counts g: a crit's hit-stop freezes 0.2 s.

SSBOT_FORUM_JB_DASH_STOP=1 (SP8 T2, follows v2; the person's second option; with JB_DASH_SLASH on, the stop goes
below combo_d_min and the stab + RS from there; one live Clapper only): from stop_d_min .. stop_d_max in front,
the dash + the key toward it held, both released so she stops in slash reach (centre to centre <= stop_u): a tap (the
dash's own 3.3 u) when that reaches, else the dash held into the ground sprint and released, closed loop on her x and
speed, inside Sprint Grace (the FSM: a release within 0.3 s of the sprint's start regains control at once, no skid;
fitted 0.183-0.283 s: the release by grace_f frames into the sprint); then side slashes every slash_cd frames, the
first with no direction key (she faces it), later ones with the key toward it on the frame before, walking in to
stop_stand between them (each hit knocks it ~0.48 u away), until the antic frame press_k_max.

SSBOT_FORUM_JB_SLAM_DASH=1 (SP8b, default off until its A/B; forum.md 73): the same stop for the jump slam's antic (Jump
Antic, 30 frames to the Jump Aim; its crouched body front 1.65 u: the standing side slash reaches <= 4.67 u centre to
centre; at its start she stands 9.25 u away, p10 / 90 8.53 / 9.76, and lands 2 hits in 52 antics, antic_audit): from
j_stop_d_min .. j_stop_d_max the dash held and released to stop at j_stop_u, then one side slash (about antic frame 20);
nearer (in reach, or a walk-in that reaches by j_press_k_max) she walks in and slashes, twice when the first press comes
early enough; then the planner (JUMP_BEHIND's aim stance and the way under). j_mode 1 (SSBOT_FORUM_JB_DASH_SET=j_mode=1):
the DashStab instead of the stop (the comparison: one hit at k0 + 15-17 from 8-12 u, she is in the recoil at the aim).
SSBOT_FORUM_JB_CORNER=1 (SP8b, with JUMP_BEHIND, default off; one live Clapper only - the lead's note: with two Clappers
SP9 switches target at the corner): the Clapper's centre within corner_from_u of the wall behind it at either jump
antic's start (the person: "after pushing it into the corner, when it does a jump move you can walk up leisurely, slash
twice, then go under to its back") and she within corner_walk_max in front: walk in and slash every slash_cd frames
through the antic (the stop script's slash phase without the dash); the way under is the planner's (JUMP_BEHIND's
behind spot with the wall rule; gauntlet: walk when it fits).

    cs = CastStab()                                   # per episode: cs.reset()
    m = cs.step(f, s, ground, accepting, t_game)      # the mask for frame f + 2, or None (the planner decides)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from ssbot.combat import jump_behind as _jb
from ssbot.combat import slam_play as _sp


def _on(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip() == "1"


# SP8a A/B (forum.md 72; 34b2b47 / 33ff9d5, 32 episodes per arm; the person's rule "the faster arm is the default, not
# worse on HP-hitless"): sp8dx (all three) landed / s 1.022 -> 1.075 (+0.053, 90 % +0.016 .. +0.089), kill p50 21.9 ->
# 20.6 s, HP-hitless 30 -> 30 of 32, the jump cast's antic 0.48 -> 1.85 hits. Unset, the three follow SSBOT_FORUM_V2
# (on with v2, off without it, like the SP4-SP6 switches); =0 turns each off (arm rnsp8a0: all three off = the SP7
# default).
_V2 = "1" if _on("SSBOT_FORUM_V2") else "0"
DASH_SLASH = _on("SSBOT_FORUM_JB_DASH_SLASH", _V2)
COMBO = DASH_SLASH and _on("SSBOT_FORUM_JB_DASH_COMBO", _V2)
STOP = _on("SSBOT_FORUM_JB_DASH_STOP", _V2)
# SP8b (forum.md 73): default off until their A/B; with them off every decision is the SP8a one
SLAM_DASH = _on("SSBOT_FORUM_JB_SLAM_DASH")
CORNER = _jb.CORNER
ENABLED = DASH_SLASH or STOP or SLAM_DASH or CORNER
CLAPPER = _sp.CLAPPER
ANTIC = ("Cast Slam Antic", "Cast Slam Antic 2")
JUMP_ANTIC = ("Jump Antic",)  # SP8b: the jump slam's antic (30 frames; Jump Aim at +30, p10 / 90 29 / 30)
J_AIM_K = 30
J_BODY_FRONT = 1.65          # its crouched body front in the Jump Antic (2.05 on its first frame; antic_audit)
M_L, M_R, M_A, M_DASH = _sp.M_L, _sp.M_R, _sp.M_A, _sp.M_DASH
SEND_AHEAD = _sp.SEND_AHEAD
BODY_FRONT = 1.873           # its body box front edge from its centre in the cast antic (u; Idle 2.25)
HALF_W = 0.23                # the hero's box half width
STAB_REACH = 3.10            # the DashStab polygon's reach in front of her transform
DASH_V, DASH_F = 28.0, 7     # the ground dash: u/s, the frames it moves (1 .. 7 after the dash's mask)
STAB_V0, STAB_V0_F, STAB_V = 26.9, 5, 17.5   # the stab's lunge straight from the dash, then the sprint speed
STAB_START = 8               # the stab clip's first frame after the dash's mask (the first sprint frame)
STAB_ON, STAB_OFF = 7, 14    # its collider active these frames after the stab starts
HIT_WAIT = 2                 # frames between the hit and the recoil: she lunges on at STAB_V (SP8 t2: 0.6 u)
HIT_LAG = 1                  # the hit may register this many frames after the model's (live j16 vs j15)
REC_VX, REC_VY, REC_DEC, REC_F = 30.0, 20.0, 0.85, 20
GRAV = 60.0                  # u/s^2 (kinematics: 60 x gravityScale 1; 1.2 u/s per 50 Hz physics step)
AIM_K = 55                   # the Jump Aim, frames from the antic start
SPRINT_V, SPRINT_DEC = 20.0, 1.1 * 50.0 / 60.0   # Ground Sprint: Sprint Speed Regular 20, AccelerateToX 1.1 / step
RS_CLIP = "Wanderer RecoilStab"
RUNE_R = 7.187               # the jump cast's rune circle (forum.md 70.7: a disc of this radius, lit 63-86 frames after
#                              its landing); a start never dashes through one that is still there (SP8 t5 ep 2: a jump
#                              cast 56 frames after the last one's landing, the stab into its circle, 2 HP)


def rune_spans(s: dict) -> list[tuple[float, float, object, bool]]:
    """The rune circles present in a STATE (damager objects with a collider of the circle's size): (x lo, x hi, iid,
    lit now). The object is there from its landing on and stays after its burst, unlit (192006 ep 1: present from the
    landing, lit + 65 .. + 71, still there 175 frames later)."""
    out = []
    for o in s.get("ents") or ():
        if o.get("type_key") != "damager" or not o.get("pos"):
            continue
        for col in o.get("colliders") or ():
            vs = col.get("verts_world") or ()
            xs = vs[0::2]
            if xs and abs((max(xs) - min(xs)) - 2 * RUNE_R) <= 0.6:
                out.append((float(min(xs)), float(max(xs)), o.get("iid"), bool(col.get("enabled"))))
                break
    return out


FLOOR_BOX = 3.015            # the floor's y under the boxes (her box bottom standing; its body box's)
RUNE_LIVE_F = 100            # a circle not seen lit yet is still to come for this many frames after it is first seen
STOP_WAIT_CLIPS = ("Sprint", "Skid", "Wanderer", "Land to Sprint")   # T2 waits these out (and "Dash" itself)


@dataclass
class StabCfg:
    press_j: int = 5             # the attack press, frames after the dash press (the dash's last frames: queued)
    hold_a: int = 2              # the attack held this many frames (one rising edge)
    k_max: int = 12              # the latest antic frame (the mask's) at which the script may start
    d_min: float = 8.0           # her centre's distance in front of its centre at the dash (u): beyond the side
    d_max: float = 12.0          # slash's walk-in (the planner walks in from nearer); stab_path decides within
    margin: float = 0.25         # STAB_MARGIN: her box front never nearer than its body front + this
    land_margin: int = -8        # LAND_MARGIN: frames before the Jump Aim (< 0: after it; her control is back
    #                                  0.34-0.48 s after the press, in the air ~2 u up, 6-8 u in front of it)
    hit_wait_max: int = 16       # no hit seen by the dash + this many frames: a miss, hand back
    end_j: int = 60              # the script ends here at the latest
    wall_room: float = 1.0       # room behind her (u) for the recoil (else no start)
    # SP8 T1 (JB_DASH_COMBO): the RecoilStab
    combo_d_min: float = 10.0    # the RS only from this far at the dash (u, centre to centre)
    rs_g0: int = 16              # the attack's first frame (game frames after the DashStab hit, the mask's frame)
    rs_g_late: int = 24          # ... the press may still come up to here (ticks skipped, or her recoil still
    #                                  carrying her out to rs_x_min)
    rs_x_min: float = 6.75       # the RS only from this far (her x at the press, centre to centre: _rs_far)
    rs_hit_g: int = 25           # the predicted RS hit after the DashStab hit (start g15-16, collider r8-10)
    rs_k_max: int = 52           # the RS hit by this antic frame (the Jump Aim at 55)
    rs_wait_g: int = 30          # no RS clip by here: no RS (hand back)
    rs_end_g: int = 45           # the RS clip running past here: hand back
    rs_block_g: int = 31         # no RS planned: no key until here (an attack press up to g30 makes one)
    post_aim_f: int = 10         # after the RS hit no key until the Jump Aim + this
    under: int = 1               # then the way under it (0: hand back to the planner at aim + post_aim_f)
    under_dash_f: int = 16       # ... the key toward it from aim + post_aim_f, the air dash at aim + this (its
    under_dash_hold: int = 4     #     body's bottom 8.2 u above the floor, her top <= 7.4) held this many frames
    under_clear: float = 2.4     # ... no key once she is this far behind its centre (its back 1.34 + 0.23 + 0.8)
    under_feet_max: float = 5.3  # ... only when her feet are at most this high at aim + post_aim_f
    under_end_f: int = 48        # ... hand back at aim + this at the latest
    prep_max: int = 3            # the start's first dash frame waits up to this many frames for the key filter
    # SP8 T2 (JB_DASH_STOP): dash, stop, side slashes
    stop_d_min: float = 6.7      # the start's distance band (u, centre to centre; below it a tap overshoots)
    stop_d_max: float = 11.3     # ... above it the release falls past grace_f
    stop_k_max: int = 14         # the latest antic frame (the mask's) at which the stop script may start
    stop_u: float = 4.4          # the target stop (centre to centre; the standing reach in the antic 4.89)
    stop_lo: float = 3.4         # no start when the predicted stop is nearer (her box front 1.3 u off its body)
    tap_f: int = 2               # a tap: the dash held this many frames (the dash runs its 0.1 s on)
    tap_room: float = 0.35       # a tap when the dash's own travel stops her within stop_u + this
    grace_f: int = 10            # the release at most this many frames into the ground sprint (0.167 s < 0.183)
    release_lag: float = 2.0     # her travel frames from the STATE to the stop (t1: 3.0 stopped 0.3-0.9 u short)
    slash_cd: int = 19           # own presses this many frames apart (the Wanderer cooldown 0.3 s = 18)
    stop_reach: float = 4.75     # a press only from here or nearer (centre to centre)
    stop_stand: float = 4.3      # between presses walk in to here ...
    stop_min_u: float = 3.4      # ... never nearer
    press_k_max: int = 50        # the last press's antic frame (the mask's)
    # SP8b JB_SLAM_DASH: the jump slam's Jump Antic (Jump Aim at +30; its crouched body front 1.65 u: the standing side
    # slash reaches <= 4.67 u centre to centre)
    j_stop_d_min: float = 6.6    # the dash-stop band (u, centre to centre, her x on the dash's frame); nearer: walk in
    j_stop_d_max: float = 11.3   # ... (past it the release falls past grace_f)
    j_stop_u: float = 4.15       # the target stop
    j_stop_lo: float = 3.4       # no start when the predicted stop is nearer
    j_reach: float = 4.5         # a press only from here or nearer
    j_stand: float = 4.1         # between presses walk in to here (her box front 2.2 u off its crouched body) ...
    j_min_u: float = 3.4         # ... never nearer
    j_press_k_max: int = 26      # the last press's antic frame (the mask's; its collider frames reach the take-off)
    j_k_max: int = 14            # the latest antic frame (the mask's) at which a jump slam script may start
    j_mode: int = 0              # 1: the DashStab (stab_path with the crouched front) instead of the stop
    j_aim_x_min: float = 5.0     # ... only when the model puts her this far in front at the aim (in the recoil)
    # SP8b JB_CORNER (both jump antics, one live Clapper)
    corner_from_u: float = 4.0   # its centre within this of the wall behind it at the antic start (push_from_u)
    corner_walk_max: float = 6.6  # she walks in from this far at most (u, centre to centre; beyond: the dash scripts)
    corner_k_max_j: int = 14     # the latest antic frame (the mask's) to start: the jump slam
    corner_k_max_c: int = 30     # ... the jump cast
    # SP8b JB_CORNER's way under (from its take-off: the landing pushed out 1.1-4.1 u toward where she stood at the
    # aim, 43-53 frames later; the behind spot by the wall rule's estimate, then never short of its x along the jump)
    corner_under_max: float = 7.0   # she in front within this at the take-off (u, centre to centre)
    corner_under_start_f: int = 8   # the start up to this many frames after the aim
    corner_under_end_f: int = 50    # hand back at aim + this at the latest
    corner_under_tol: float = 0.2   # at the behind spot within this: no key
    corner_head_gap: float = 0.35   # its body's bottom this far above her head to pass under it (dash or walk)
    corner_dash_wait: int = 10      # no walk that fits and no dash allowed by aim + this: the planner


def _num_env(c: StabCfg) -> StabCfg:
    """SSBOT_FORUM_JB_DASH_SET="stop_u=4.2,rs_g0=15": trial overrides of the numbers above."""
    for kv in os.environ.get("SSBOT_FORUM_JB_DASH_SET", "").replace(";", ",").split(","):
        if "=" not in kv:
            continue
        k, v = (x.strip() for x in kv.split("=", 1))
        if not hasattr(c, k):
            raise KeyError(f"SSBOT_FORUM_JB_DASH_SET: unknown key {k!r}")
        cur = getattr(c, k)
        setattr(c, k, type(cur)(float(v)))
    return c


def stab_path(x0: float, cfg: StabCfg | None = None, front: float = BODY_FRONT) -> dict:
    """The dash slash from x0 u in front of its centre (centre to centre), the dash's mask on frame 0: the predicted
    frame of the hit (None: no hit), her nearest x (centre), the recoil's top height, the landing frame, and the path
    [(j, x, y)] (frames from the dash's mask; x in front of its centre, y above the floor)."""
    x, y, path = x0, 0.0, [(0, x0, 0.0)]
    for j in range(1, STAB_START):
        x -= DASH_V / 60.0
        path.append((j, x, y))
    hit, xmin = None, x
    j = STAB_START
    for i in range(STAB_OFF + 1):
        x -= (STAB_V0 if i < STAB_V0_F else STAB_V) / 60.0
        xmin = min(xmin, x)
        path.append((j, x, y))
        if i >= STAB_ON and x - STAB_REACH <= front:
            hit = j
            break
        j += 1
    if hit is None:
        return {"hit": None, "xmin": xmin, "path": path, "land": None, "top": 0.0}
    for _ in range(HIT_WAIT):
        j += 1                                    # she lunges on at the sprint speed (SP8 t2 ep 0: from 2.59 u at the
        x -= STAB_V / 60.0                        # hit to 1.98 two frames later, into its body: 2 HP), then -30
        path.append((j, x, y))
    xmin = min(xmin, x - HIT_LAG * STAB_V / 60.0)
    vx, vy = REC_VX, REC_VY
    for _ in range(REC_F):
        j += 1
        x += vx / 60.0
        y += vy / 60.0
        vx *= REC_DEC
        vy *= REC_DEC
        path.append((j, x, y))
    top, vy = y, 0.0
    while y > 0.0:
        j += 1
        vy -= GRAV / 60.0
        y = max(0.0, y + vy / 60.0)
        path.append((j, x, y))
    return {"hit": hit, "xmin": xmin, "path": path, "land": j, "top": top}


def sprint_travel(j: int) -> float:
    """Her travel (u) by frame j after a dash's mask with the dash held all the way: the dash (frames 1 .. DASH_F at
    28 u/s), then the ground sprint slowing from 28 toward SPRINT_V by AccelerateToX's 1.1 u/s per physics step."""
    d, v = 0.0, DASH_V
    for jj in range(1, j + 1):
        if jj > DASH_F:
            v = max(SPRINT_V, v - SPRINT_DEC)
        d += v / 60.0
    return d


def _clean(latch, m: int) -> bool:
    """The direction and dash keys of m latch as sent (no latch callable: yes)."""
    if latch is None:
        return True
    keys = M_L | M_R | M_DASH
    return (int(latch(m)) & keys) == (m & keys)


def stop_plan(x0: float, cfg: StabCfg, stop_u: float | None = None, stop_lo: float | None = None) -> dict | None:
    """T2: how she stops in reach from x0 (centre to centre): a tap (the dash's own travel) or the dash held to the
    frame jr (the first frame without it) - None when neither stops her inside [stop_lo, stop_u + tap_room] in time.
    stop_u / stop_lo: the cfg's (the cast antic) unless given (SP8b: the jump slam's j_stop_u / j_stop_lo)."""
    c = cfg
    su = c.stop_u if stop_u is None else stop_u
    lo = c.stop_lo if stop_lo is None else stop_lo
    x_tap = x0 - sprint_travel(DASH_F)
    if lo <= x_tap <= su + c.tap_room:
        return {"tap": True, "jr": c.tap_f, "x_stop": round(x_tap, 2)}
    if x_tap < lo:
        return None
    for jr in range(DASH_F + 1, DASH_F + c.grace_f + 1):
        x_stop = x0 - sprint_travel(jr + 1)        # she moves on through the release's own frame
        if x_stop <= su:
            return {"tap": False, "jr": jr, "x_stop": round(x_stop, 2)} if x_stop >= lo else None
    return None


@dataclass
class Stab:
    iid: object
    face: int                   # its facing (+1 right)
    j0: int                     # the STATE frame of the dash's mask (frame j = 0 is f0 + SEND_AHEAD)
    k0: int                     # the antic frame of the dash
    x0: float
    pred: dict = field(default_factory=dict)
    phase: str = "lunge"        # stab: lunge / recoil / rs / post; stop: dash / stop / slash; then done / abort
    why: str = ""
    hit_f: int | None = None
    hp0: int = 0
    mode: str = "stab"          # stab (SP6 / T1) or stop (T2)
    ta: float = 0.0             # the antic's start on the game clock (s)
    rs: bool = False            # T1: the RecoilStab planned
    t_hit: float | None = None  # the DashStab hit's game time
    k_hit: float | None = None
    rs_sent: int = 0
    rs_start_g: float | None = None
    rs_hit_g: float | None = None
    rs_x: float | None = None   # T1: her farthest x at the RS press check (u, centre to centre)
    t_aim: float | None = None
    rel_j: int | None = None    # T2: the release frame (j)
    x_stop: float | None = None
    presses: list = field(default_factory=list)   # antic frames of own presses (the mask's)
    last_m: int = 0
    hits: list = field(default_factory=list)      # (antic frame, src) of landed hits while it ran
    skid: bool = False
    stab_in_stop: bool = False
    at_aim: dict | None = None
    prep: int = 0               # frames waited for the key filter before the dash
    x_aim_cx: float | None = None   # its centre and her transform x at the aim (the landing's prediction)
    hx_aim: float | None = None
    under: dict | None = None   # T1's way under: start / dash / clear frames (from the aim), her height
    kind: str = "cast"          # SP8b: "jump" (the jump slam's Jump Antic) or "cast" (the jump cast's antic)
    walk: bool = False          # SP8b: no dash - she starts in reach or walks in (the first press with the key toward it)
    corner: bool = False        # SP8b JB_CORNER's run


class CastStab:
    def __init__(self, cfg: StabCfg | None = None, dash_slash: bool | None = None, combo: bool | None = None,
                 stop: bool | None = None, slam_dash: bool | None = None, corner: bool | None = None):
        self.cfg = cfg or _num_env(StabCfg())
        self.dash_slash = DASH_SLASH if dash_slash is None else dash_slash
        self.combo = (COMBO if combo is None else combo) and self.dash_slash
        self.stop = STOP if stop is None else stop
        self.slam_dash = SLAM_DASH if slam_dash is None else slam_dash      # SP8b: the jump slam's antic
        self.corner = CORNER if corner is None else corner                  # SP8b: either jump antic at a wall
        if dash_slash is None and stop is None and not (self.dash_slash or self.stop):
            self.dash_slash = True               # constructed directly (tests, probes): the SP6 dash slash
        self.run: Stab | None = None
        self.done: list[Stab] = []
        self._seen: set = set()            # (iid, antic entry frame) looked at
        self.n_antic = 0
        self.n_jantic = 0                  # SP8b: jump slam antics looked at
        self._jump_kind: dict = {}         # SP8b JB_CORNER: Clapper iid -> the antic kind seen, until its take-off
        self.why_not: dict = {}
        self._pred: dict = {}
        self._runes: dict = {}             # rune circle iid -> {"first": frame first seen, "lit": seen lit}

    def reset(self) -> None:
        self.run = None
        self.done = []
        self._seen = set()
        self.n_antic = 0
        self.n_jantic = 0
        self._jump_kind = {}
        self.why_not = {}
        self._runes = {}

    def observe(self, f: int, s: dict) -> None:
        """Every tick (the policy calls it while the slam playbook runs too): the rune circles' first frame and lit
        state."""
        self._rune_threats(f, s)

    def _rune_threats(self, f: int, s: dict) -> list[tuple[float, float]]:
        """The x spans of the rune circles that are lit now or still to come (present, not yet seen lit, and first
        seen less than RUNE_LIVE_F frames ago); a burst one stays as an unlit object and is no threat."""
        out = []
        for lo, hi, iid, lit in rune_spans(s):
            r = self._runes.setdefault(iid, {"first": f, "lit": False})
            if lit:
                r["lit"] = True
                out.append((lo, hi))
            elif not r["lit"] and f - r["first"] < RUNE_LIVE_F:
                out.append((lo, hi))
        return out

    def stats(self) -> dict:
        from collections import Counter
        out = Counter({"antics": self.n_antic})
        if self.slam_dash or self.corner:
            out["j_antics"] = self.n_jantic
        for r in self.done + ([self.run] if self.run is not None else []):
            if r.mode == "under":                                              # SP8b JB_CORNER's way under
                out["corner_under"] += 1
                out["corner_under_there"] += bool(r.under and r.under.get("there") is not None)
                out["corner_under_dash"] += bool(r.under and r.under.get("dash") is not None)
                out[f"corner_under_end_{r.phase}_{r.why}"] += 1
                continue
            pre = "corner_" if r.corner else "j_" if r.kind == "jump" else ""     # SP8b's runs apart
            out[pre + ("stabs" if r.mode == "stab" else "stops")] += 1
            if r.mode == "stab":
                out[pre + "hit"] += r.hit_f is not None
                out[pre + "rs_planned"] += r.rs
                out[pre + "rs_started"] += r.rs_start_g is not None
                out[pre + "rs_hit"] += r.rs_hit_g is not None
            else:
                out[pre + "stop_presses"] += len(r.presses)
                out[pre + "stop_skid"] += r.skid
                out[pre + "stop_stab"] += r.stab_in_stop
            out[pre + "hits_in_script"] += len(r.hits)
            out[f"{pre}end_{r.phase}"] += 1
            if r.why:
                out[f"{pre}why_{r.why}"] += 1
        for k, v in self.why_not.items():
            out[f"no_{k}"] += v
        res = dict(out)
        if self.combo or self.stop or self.slam_dash or self.corner:
            res["runs"] = [self._rec(r) for r in self.done + ([self.run] if self.run is not None else [])]
        return res

    @staticmethod
    def _rec(r: Stab) -> dict:
        d = {"mode": r.mode, "f0": r.j0 - SEND_AHEAD, "k0": r.k0, "x0": r.x0, "rs": r.rs, "k_hit": r.k_hit,
             "rs_start_g": r.rs_start_g, "rs_x": r.rs_x,
             "rs_hit_g": r.rs_hit_g, "rel_j": r.rel_j, "x_stop": r.x_stop, "presses": r.presses, "hits": r.hits,
             "skid": r.skid, "stab_in_stop": r.stab_in_stop, "end": r.phase, "why": r.why, "at_aim": r.at_aim,
             "pred": r.pred, "prep": r.prep, "under": r.under}
        if r.kind != "cast" or r.walk or r.corner:
            d.update({"kind": r.kind, "walk": r.walk, "corner": r.corner})      # SP8b
        return d

    @staticmethod
    def _states(r: Stab) -> tuple:
        """The run's antic states (SP8b: the jump slam's Jump Antic, else the jump cast's two)."""
        return JUMP_ANTIC if r.kind == "jump" else ANTIC

    def _lim(self, r: Stab) -> tuple[float, float, float, int]:
        """The slash phase's (reach, stand, nearest, last press antic frame) for the run's antic."""
        c = self.cfg
        if r.kind == "jump":
            return c.j_reach, c.j_stand, c.j_min_u, c.j_press_k_max
        return c.stop_reach, c.stop_stand, c.stop_min_u, c.press_k_max

    def active(self) -> bool:
        return self.run is not None and self.run.phase not in ("done", "abort")

    def abort(self, why: str) -> None:
        if self.active():
            self._close("abort", why)

    def _close(self, phase: str, why: str = "") -> None:
        r = self.run
        if r is not None:
            r.phase, r.why = phase, r.why or why
            self.done.append(r)
        self.run = None

    def step(self, f: int, s: dict, ground: bool, accepting: bool = True, t_game: float | None = None,
             latch=None) -> int | None:
        """The mask for frame f + 2 while a script runs, else None. t_game: the game clock (s; Stamp.t_game_s, still
        through hit-stop freezes); None: f / 60 (tests). latch: m -> the key mask the game latches at f + 2 when m is
        sent for it (the oracle's hold filter: a key stays down 2 frames, up 2 frames, never left and right at once;
        SP8 t1: a planner key away from it on the frame before the start turned the first dash frame away, 1 of 7
        stabs); None: m itself."""
        c = self.cfg
        t = f / 60.0 if t_game is None else float(t_game)
        e = _sp.clapper(s)
        st, tin = _sp.control(e)
        h = s.get("hero") or {}
        hp = int(h.get("health") or 0)
        r = self.run
        if r is not None:
            if hp < r.hp0:
                self._close("abort", "hurt")
                return None
            if e is None or e.get("iid") != r.iid:
                self._close("abort", "gone")
                return None
            for ev in s.get("ev") or ():
                d = ev.get("d") or {}
                if ev.get("k") == "hit" and d.get("type_key") == CLAPPER:
                    dealt = d.get("dealt", d.get("amount"))
                    if dealt is None or float(dealt) > 0:
                        r.hits.append((round((t - r.ta) * 60.0, 1), str(d.get("src"))))
            if r.t_aim is None and st not in self._states(r):
                r.t_aim = t - (tin if st in ("Cast Jump", "Jump Aim") else 0.0)
                r.x_aim_cx = float(e["pos"][0])
                r.hx_aim = float((h.get("pos") or [_sp.hero_x(s)])[0])
                b = h.get("box")
                if b:
                    r.at_aim = {"x": round((_sp.hero_x(s) - float(e["pos"][0])) * r.face, 2),
                                "feet": round(float(b[1]) - 3.015, 2), "clip": str((h.get("anim") or {}).get("clip"))}
            if r.phase == "prep":
                m = self._step_prep(r, f, t, s, e, st, tin, ground, accepting, latch)
            elif r.mode == "under":
                m = self._step_cunder(r, f, t, s, e, st, ground)
            else:
                m = self._step_stop(r, f, t, s, e, st, ground, accepting) if r.mode == "stop" else \
                    self._step_stab(r, f, t, s, e, st, ground)
            if m is not None:
                r.last_m = m
            return m
        # a new start?
        if e is None:
            return None
        if self.corner:
            # SP8b JB_CORNER: the way under a jump at a wall starts at its take-off (one look per jump whose antic was
            # seen)
            if st in ("Cast Slam Antic", "Cast Slam Antic 2", JUMP_ANTIC[0]):
                self._jump_kind[e.get("iid")] = "jump" if st == JUMP_ANTIC[0] else "cast"
            elif st in ("Jump", "Air") and e.get("iid") in self._jump_kind:
                return self._start_under(f, t, s, e, st, tin, ground, hp)
        if st == "Cast Slam Antic":
            kind = "cast"
        elif st == JUMP_ANTIC[0] and (self.slam_dash or self.corner):
            kind = "jump"                                   # SP8b: the jump slam's antic
        else:
            return None
        ka = int(round(tin * 60.0)) + SEND_AHEAD          # the antic frame the next mask lands on
        key = (e.get("iid"), f - int(round(tin * 60.0)))
        if key in self._seen:
            return None
        why = self._why_start(s, e, ground, accepting, ka, kind)
        if why is not None:
            if why != "wait":
                self._seen.add(key)
                if kind == "cast":
                    self.n_antic += 1
                    self.why_not[why] = self.why_not.get(why, 0) + 1
                else:
                    self.n_jantic += 1
                    self.why_not["j_" + why] = self.why_not.get("j_" + why, 0) + 1
            return None
        self._seen.add(key)
        if kind == "cast":
            self.n_antic += 1
        else:
            self.n_jantic += 1
        face = 1 if e.get("flipX") else -1
        x0 = (_sp.hero_x(s) - float(e["pos"][0])) * face
        p = self._pred
        mode = p.get("mode", "stab")
        self.run = Stab(iid=e.get("iid"), face=face, j0=f + SEND_AHEAD, k0=ka, x0=round(x0, 3), pred=p, hp0=hp,
                        mode=mode, ta=t - tin, rs=bool(p.get("rs")), phase="lunge" if mode == "stab" else "dash",
                        kind=kind, walk=bool(p.get("walk")), corner=bool(p.get("corner")))
        if self.run.walk:
            # SP8b: in reach or walking in - the slash phase at once (no dash)
            self.run.phase = "slash"
            m = self._step_stop(self.run, f, t, s, e, st, ground, accepting)
            if m is not None:
                self.run.last_m = m
            return m
        toward = M_R if -face > 0 else M_L
        if not _clean(latch, toward | M_DASH):
            self.run.phase = "prep"              # the key toward it first: the dash on the first clean frame
            self.run.prep = 1
            self.run.last_m = toward
            return toward
        self.run.last_m = toward | M_DASH
        return toward | M_DASH

    def _step_prep(self, r: Stab, f: int, t: float, s: dict, e: dict, st: str | None, tin: float, ground: bool,
                   accepting: bool, latch) -> int | None:
        """The start's key-filter wait: the key toward it until toward + dash latch together, then the script from
        that frame (its start conditions checked again at the new antic frame and distance)."""
        toward = M_R if -r.face > 0 else M_L
        if not _clean(latch, toward | M_DASH):
            if r.prep >= self.cfg.prep_max:
                self._close("abort", "prep")
                return None
            r.prep += 1
            return toward
        if st != self._states(r)[0]:
            self._close("abort", "prep late")
            return None
        ka = int(round(tin * 60.0)) + SEND_AHEAD
        why = self._why_start(s, e, ground, accepting, ka, r.kind)
        if why is None and bool(self._pred.get("walk")):
            why = "walk"                                  # SP8b: in reach / walk-in band by now: not this dash
        if why is not None or self._pred.get("mode", "stab") != r.mode:
            self._close("abort", f"prep {why or 'mode'}")
            return None
        x0 = (_sp.hero_x(s) - float(e["pos"][0])) * r.face
        r.j0, r.k0, r.x0, r.pred, r.rs = f + SEND_AHEAD, ka, round(x0, 3), self._pred, bool(self._pred.get("rs"))
        r.phase = "lunge" if r.mode == "stab" else "dash"
        return toward | M_DASH

    # ---- the dash slash (SP6) and the RecoilStab (SP8 T1) ----

    def _step_stab(self, r: Stab, f: int, t: float, s: dict, e: dict, st: str | None, ground: bool) -> int | None:
        c = self.cfg
        h = s.get("hero") or {}
        clip = str((h.get("anim") or {}).get("clip") or "")
        j = f + SEND_AHEAD - r.j0                     # frames since the dash's mask
        evs = [(ev.get("d") or {}) for ev in s.get("ev") or () if ev.get("k") == "hit"
               and (ev.get("d") or {}).get("type_key") == CLAPPER]
        if r.hit_f is None and any("Dash" in str(d.get("src")) for d in evs):
            r.hit_f, r.phase, r.t_hit = f, "recoil", t
            r.k_hit = round((t - r.ta) * 60.0, 1)
            if r.rs and r.k_hit + c.rs_hit_g > c.rs_k_max:
                r.rs, r.why = False, "rs late"
        if r.phase == "lunge":
            if j > c.hit_wait_max + STAB_START:
                self._close("done", "miss")
                return 0                                 # release the dash (a held one sprints on into it)
            toward = M_R if -r.face > 0 else M_L
            m = toward | M_DASH                          # the dash held: the sprint, the stab from it
            if c.press_j <= j < c.press_j + c.hold_a:
                m |= M_A
            return m
        g = round((t - r.t_hit) * 60.0)                  # game frames since the DashStab hit (this STATE; dt 16.65 ms)
        # on the ground only after the hop (SP6 read the stab's own ground frame at the hit and handed back at once:
        # t6's 9 stabs all ended "landed" on the hit's tick; her recoil takes no input until ~g21 anyway)
        landed = ground and f - r.hit_f >= 6
        if r.phase == "recoil":
            if not r.rs:
                # SP6: no key until her control returns (the recoil clip over), then the planner - SP8: not before
                # the RecoilStab's window closes (a planner attack at g26-30 after control came back made an
                # unplanned RS at antic 54, t2 ep 1: she bounced at its face at the aim, fled into the rune circle)
                if (g >= c.rs_block_g and "Recoil" not in clip) or landed or j > c.end_j:
                    self._close("done", "landed" if landed else "control")
                    return None
                return 0
            if clip.startswith(RS_CLIP):
                r.phase, r.rs_start_g = "rs", round(g, 1)
            else:
                if g > c.rs_wait_g or landed:
                    self._close("done", "no rs")
                    return None
                gm = g + SEND_AHEAD                      # the mask's frame
                if r.rs_sent == 0 and gm > c.rs_g_late:
                    # never far enough: no RS - the stab's own recoil rule (no key until g31, then the planner)
                    r.rs, r.why = False, "rs near"
                    return 0
                if r.rs_sent < c.hold_a and c.rs_g0 <= gm and (r.rs_sent > 0 or self._rs_far(r, s, e)):
                    r.rs_sent += 1
                    return M_A                           # a new press: the RecoilStab (no direction, no dash)
                return 0
        if r.phase == "rs":
            hit_ev = any(str(d.get("src")) == "RecoilStab" for d in evs)
            # its clip ends early on a hit (DownSpikeBounce / Recoil Twirl, the person's RS); a miss lunges on to the
            # floor (control back at r17-18)
            short = not clip.startswith(RS_CLIP) and g - (r.rs_start_g or g) < 14
            if hit_ev or short:
                r.phase, r.rs_hit_g = "post", round(g, 1)
                if not hit_ev:
                    r.why = "rs hit unseen"
            elif not clip.startswith(RS_CLIP) or g > c.rs_end_g:
                self._close("done", "rs miss" if g <= c.rs_end_g else "rs long")
                return None
            else:
                return 0
        if r.phase == "post":
            # the bounce: no key until the Jump Aim + post_aim_f (its body rises in place in front of her)
            if ground and g > (r.rs_hit_g or 0) + 6:
                self._close("done", "landed")
                return None
            if r.t_aim is not None and round((t - r.t_aim) * 60.0) + SEND_AHEAD >= c.post_aim_f:
                why = self._why_not_under(r, s, st)
                if why is not None:
                    self._close("done", f"post ({why})")
                    return None
                b = h.get("box")
                r.phase, r.under = "under", {"f0": round((t - r.t_aim) * 60.0) + SEND_AHEAD,
                                             "feet": round(float(b[1]) - 3.015, 2) if b else None,
                                             "x": round((_sp.hero_x(s) - float(e["pos"][0])) * r.face, 2)}
            elif st is not None and st not in ANTIC and st not in ("Cast Jump", "Jump Aim", "Jump", "Air"):
                self._close("done", "post")
                return None
            else:
                return 0
        if r.phase == "under":
            return self._step_under(r, t, s, e, st, ground)
        return None

    def _rs_far(self, r: Stab, s: dict, e: dict) -> bool:
        """The RS from here clears its body: her x (centre to centre, on the mask's frame) at least rs_x_min. The RS
        lunges 3.4 u (p50; 2.9-4.3 by its collider frame r9-11) before it hits (SP8 t1-t4 and A/B, 42 RS): from 5.8
        and 6.06 u it reached its body at r10 (x 1.47 / 1.73 at the hit, 2 HP each); from >= 6.75 u 21 of 21 hit at
        >= 3.47 u."""
        h = s.get("hero") or {}
        xr = (_sp.hero_x(s) - float(e["pos"][0])) * r.face
        xr += float((h.get("vel") or [0.0, 0.0])[0]) * r.face * SEND_AHEAD / 60.0
        if r.rs_x is None or xr > r.rs_x:
            r.rs_x = round(xr, 2)
        return xr >= self.cfg.rs_x_min

    def _why_not_under(self, r: Stab, s: dict, st: str | None) -> str | None:
        """T1's way under after the RS bounce: None when it goes, else why not (the planner then)."""
        c = self.cfg
        if not c.under:
            return "off"
        if st not in ("Cast Jump", "Jump Aim", "Jump", "Air"):
            return "state"
        b = (s.get("hero") or {}).get("box")
        if not b or float(b[1]) - 3.015 > c.under_feet_max:
            return "high"
        if r.x_aim_cx is None or r.hx_aim is None:
            return "no aim"
        land = _jb.landing(r.x_aim_cx, r.hx_aim, r.face)
        if _jb.behind_spot(land, r.face) is None:
            return "no room behind"
        return None

    def _step_under(self, r: Stab, t: float, s: dict, e: dict, st: str | None, ground: bool) -> int | None:
        """The key toward it, the air dash under its rising body at aim + under_dash_f, toward until she is
        under_clear behind its centre, then no key; the planner on the ground (or at aim + under_end_f)."""
        c = self.cfg
        ua = round((t - r.t_aim) * 60.0) + SEND_AHEAD          # the mask's frame from the aim
        xr = (_sp.hero_x(s) - float(e["pos"][0])) * r.face
        u = r.under
        if (ground and ua > u["f0"] + 2) or ua > c.under_end_f or st not in ("Cast Jump", "Jump Aim", "Jump", "Air"):
            self._close("done", "under landed" if ground else "under end")
            return None
        if xr <= -c.under_clear or u.get("clear") is not None:
            u.setdefault("clear", ua)
            return 0
        toward = M_R if -r.face > 0 else M_L
        if c.under_dash_f <= ua < c.under_dash_f + c.under_dash_hold:
            u.setdefault("dash", ua)
            return toward | M_DASH
        return toward

    # ---- SP8b JB_CORNER: the way under a jump at a wall ----

    @staticmethod
    def _body(e: dict) -> tuple[float, float, float] | None:
        """Its body collider ("Song Heavy Sentry", damage on): (x lo, x hi, bottom above the floor), or None."""
        for col in e.get("colliders") or ():
            if col.get("name") == CLAPPER and col.get("enabled", True) and col.get("verts_world"):
                vs = col["verts_world"]
                xs, ys = vs[0::2], vs[1::2]
                return float(min(xs)), float(max(xs)), float(min(ys)) - FLOOR_BOX
        return None

    def _start_under(self, f: int, t: float, s: dict, e: dict, st: str, tin: float, ground: bool,
                     hp: int) -> int | None:
        """At its take-off (the first Jump / Air tick after an antic seen): the way under when its centre is within
        corner_from_u of the wall behind it, one live Clapper, she on the ground in front within corner_under_max and
        the wall rule's landing leaves a behind spot."""
        c = self.cfg
        iid = e.get("iid")
        kind = self._jump_kind.pop(iid, "jump")
        face = 1 if e.get("flipX") else -1
        cx = float(e["pos"][0])
        h = s.get("hero") or {}
        hx = _sp.hero_x(s)
        since = (tin + (1.0 / 60.0 if st == "Air" else 0.0)) * 60.0       # frames since the aim (Jump: 1 frame)
        x_rel = (hx - cx) * face
        b = h.get("box")
        feet = float(b[1]) - FLOOR_BOX if b else 0.0
        land = _jb.landing(cx, float((h.get("pos") or [hx])[0]), face)
        why = None
        if _jb.corner_room(cx, face) >= c.corner_from_u:
            why = "not corner"
        elif len(_sp.clappers(s)) != 1:
            why = "two"
        elif since > c.corner_under_start_f:
            why = "late"
        elif x_rel <= 0:
            why = "behind"
        elif x_rel > c.corner_under_max:
            why = "far"
        elif feet > 0.6:
            why = "air"
        elif _jb.behind_spot(land, face) is None:
            why = "no room"
        if why is not None:
            self.why_not["under_" + why] = self.why_not.get("under_" + why, 0) + 1
            return None
        r = Stab(iid=iid, face=face, j0=f + SEND_AHEAD, k0=0, x0=round(x_rel, 3), hp0=hp, mode="under", ta=t,
                 phase="under", kind=kind, corner=True,
                 pred={"mode": "under", "land": round(land, 2), "room0": round(_jb.corner_room(cx, face), 2)})
        r.t_aim = t - since / 60.0
        r.x_aim_cx, r.hx_aim = cx, hx
        r.at_aim = {"x": round(x_rel, 2), "feet": round(feet, 2), "clip": str((h.get("anim") or {}).get("clip"))}
        r.under = {"x0c": cx, "land": land, "f0": round(since, 1)}
        self.run = r
        m = self._step_cunder(r, f, t, s, e, st, ground)
        if m is not None:
            r.last_m = m
        return m

    def _step_cunder(self, r: Stab, f: int, t: float, s: dict, e: dict, st: str | None, ground: bool) -> int | None:
        """Toward the wall to the behind spot of the (pushed-out) landing: a walk when it gets her past its back
        (walk_clear_u) by aim + corner_walk_end_f, else one ground dash under its body while it is high (rising, or
        its bottom well above her head); never into its body's x span while its bottom is below her head + the gap;
        no key once there; the planner when it lands or at aim + corner_under_end_f."""
        c = self.cfg
        h = s.get("hero") or {}
        u = r.under
        toward = M_R if -r.face > 0 else M_L
        cx = float(e["pos"][0])
        hx = _sp.hero_x(s)
        since = (t - r.t_aim) * 60.0 + SEND_AHEAD          # the mask's frame from the aim
        if st not in ("Jump", "Air"):
            self._close("done", "landed" if (hx - cx) * r.face < 0 else "landed front")
            return None
        if since > c.corner_under_end_f:
            self._close("done", "end")
            return None
        if (cx - u["x0c"]) * r.face > 0.05 and (cx - u["land"]) * r.face > 0:
            u["land"] = cx                                 # pushed out past the estimate (the wall-top ledge)
        land = u["land"]
        spot = _jb.behind_spot(land, r.face)
        if spot is None:
            self._close("abort", "no room")
            return None
        d = (hx - spot) * r.face                           # still to go toward the wall (u)
        if d <= c.corner_under_tol:
            u.setdefault("there", round(since, 1))
            return 0
        if u.get("dash") is not None and since - u["dash"] < c.tap_f:
            return toward | M_DASH                         # the dash tap's second frame
        b = h.get("box")
        top = (float(b[3]) - FLOOR_BOX) if b else 2.07
        body = self._body(e)
        vy = float((e.get("vel") or [0.0, 0.0])[1]) if e.get("vel") else 0.0
        high = body is None or body[2] >= top + c.corner_head_gap
        lo_n, hi_n = (float(b[0]), float(b[2])) if b else (hx - HALF_W, hx + HALF_W)
        step = -r.face * _sp.WALK_U
        under_now = body is not None and lo_n < body[1] and hi_n > body[0]
        under_next = body is not None and lo_n + step < body[1] and hi_n + step > body[0]
        if under_next and not under_now and not high:
            u["held"] = u.get("held", 0) + 1
            return 0                                       # never under its falling (or still low) body
        need = (hx - land) * r.face + _jb.CFG["walk_clear_u"]
        walk_fits = need <= _jb.CFG["walk_v"] * (_jb.CFG["corner_walk_end_f"] - since)
        tm = h.get("tm") or {}
        dash_ok = (u.get("dash") is None and ground and float(tm.get("dash_cd") or 0.0) <= 0.02 and high
                   and (vy >= 0.0 or body is None or body[2] >= top + 1.5))
        if not walk_fits and dash_ok:
            u["dash"] = round(since, 1)
            return toward | M_DASH
        if not walk_fits and u.get("dash") is None and since > c.corner_dash_wait:
            self._close("abort", "no way")                 # no walk in time and no dash: the planner (back off)
            return None
        return toward

    # ---- dash, stop, side slashes (SP8 T2) ----

    def _step_stop(self, r: Stab, f: int, t: float, s: dict, e: dict, st: str | None, ground: bool,
                   accepting: bool) -> int | None:
        c = self.cfg
        h = s.get("hero") or {}
        clip = str((h.get("anim") or {}).get("clip") or "")
        j = f + SEND_AHEAD - r.j0
        toward = M_R if -r.face > 0 else M_L
        cx = float(e["pos"][0])
        xr = (_sp.hero_x(s) - cx) * r.face                # her x in front of it now (centre to centre)
        km = round((t - r.ta) * 60.0) + SEND_AHEAD        # the mask's antic frame
        if clip.startswith("Skid"):
            r.skid = True
        if clip.startswith("Wanderer Dash Attack") or clip.startswith("Wanderer DashRecoil"):
            r.stab_in_stop = True
        if r.phase == "dash":
            if r.pred.get("tap"):
                if j < c.tap_f:
                    return toward | M_DASH
                r.phase, r.rel_j = "stop", j
                return 0
            v = abs(float((h.get("vel") or [0.0, 0.0])[0]))
            stop_u = c.j_stop_u if r.kind == "jump" else c.stop_u
            # closed loop: release when her travel through the mask's frame and the release frame ends at stop_u
            if j > DASH_F and (xr - c.release_lag * v / 60.0 <= stop_u or j > DASH_F + c.grace_f):
                r.phase, r.rel_j = "stop", j
                if j > DASH_F + c.grace_f:
                    r.why = "late release"
                return 0
            if j > DASH_F + c.grace_f + 4:
                r.phase, r.rel_j = "stop", j
                return 0
            return toward | M_DASH
        if r.phase == "stop":
            # wait for her control: on the ground, accepting input, out of the dash / sprint / skid clips (she accepts
            # input in the Dash clip itself: SP6 t6)
            if ground and accepting and clip != "Dash" and not clip.startswith(STOP_WAIT_CLIPS):
                r.phase = "slash"
                r.x_stop = round(xr, 2)
            elif j > c.end_j:
                self._close("done", "no control")
                return None
            else:
                return 0
        if r.phase == "slash":
            states = self._states(r)
            reach, stand, min_u, k_max = self._lim(r)
            if st not in states or km > k_max + 2:
                self._close("done", "aim" if st not in states else "end")
                return None
            last = r.presses[-1] if r.presses else None
            if last is not None and km - last < 1.5:
                return M_A | (toward if len(r.presses) > 1 or r.walk else 0)     # the press's second frame
            if (r.kind == "jump" or r.walk) and last is not None and last + c.slash_cd > k_max:
                # SP8b: no press fits before the aim any more - the planner (its aim stance, the way under)
                self._close("done", "last press")
                return None
            cd = float(((h.get("tm") or {}).get("atk_cd")) or 0.0) * 60.0 - (SEND_AHEAD - 1)
            ready = (last is None or km - last >= c.slash_cd) and cd <= 0.05 and accepting and ground
            v = float((h.get("vel") or [0.0, 0.0])[0]) * r.face
            x_m = xr + v * SEND_AHEAD / 60.0              # her x at the mask's frame (her own velocity)
            in_reach = x_m <= reach and km <= k_max
            if ready and in_reach:
                if not r.presses and not r.walk:
                    r.presses.append(round(km, 1))
                    return M_A                            # the first press: no key (she faces it from the dash)
                fc = h.get("facing")
                facing = fc is not None and float(fc) * -r.face > 0
                if r.last_m & toward or (r.walk and not r.presses and facing):
                    r.presses.append(round(km, 1))
                    return M_A | toward
                return toward                             # the frame before the press: toward it
            if x_m - _sp.WALK_U >= stand and x_m - _sp.WALK_U >= min_u:
                return toward                             # walk in between presses
            return 0
        return None

    # ---- the start ----

    def _why_start(self, s: dict, e: dict, ground: bool, accepting: bool, ka: int, kind: str) -> str | None:
        """None when a script starts now (self._pred says which); "wait" to look again next tick; else why not. The
        jump cast's antic: SP8b's corner first (it walks in from below the T1 / T2 bands), then SP6 / SP8a as before."""
        if kind == "jump":
            return self._why_not_jump(s, e, ground, accepting, ka)
        if self.corner:
            wc = self._why_corner(s, e, ground, accepting, ka, kind)
            if wc is None or wc == "wait":
                return wc
        return self._why_not(s, e, ground, accepting, ka)

    def _x_dash(self, s: dict, e: dict) -> tuple[int, float, float]:
        """(its facing, her x in front of its centre now, the same on the mask's frame: her own velocity on)."""
        face = 1 if e.get("flipX") else -1
        x_now = (_sp.hero_x(s) - float(e["pos"][0])) * face
        v = float(((s.get("hero") or {}).get("vel") or [0.0, 0.0])[0])
        return face, x_now, x_now + v * face * SEND_AHEAD / 60.0

    def _rune_in_way(self, s: dict, e: dict, face: int, front_u: float) -> bool:
        cx = float(e["pos"][0])
        hx = _sp.hero_x(s)
        front = cx + face * front_u
        lo, hi = min(hx, front), max(hx, front)
        return any(a < hi and b > lo for a, b in self._rune_threats(int(s.get("f") or 0), s))

    def _why_corner(self, s: dict, e: dict, ground: bool, accepting: bool, ka: int, kind: str) -> str | None:
        """SP8b JB_CORNER: its centre within corner_from_u of the wall behind it, one live Clapper, she on the ground in
        front within corner_walk_max: the slash phase at once (walk in, a press every slash_cd frames)."""
        c = self.cfg
        face, x_now, x0 = self._x_dash(s, e)
        cx = float(e["pos"][0])
        room0 = (cx - _sp.WALL_L) if face > 0 else (_sp.WALL_R - cx)
        if room0 >= c.corner_from_u:
            return "not corner"
        if len(_sp.clappers(s)) != 1:
            return "corner two"
        if x_now <= 0:
            return "corner behind"
        if x0 > c.corner_walk_max:
            return "corner far"
        reach, _, min_u, k_max = self._lim(Stab(iid=None, face=face, j0=0, k0=0, x0=0.0, kind=kind))
        if x0 < min_u:
            return "corner near"                         # nearer than the stance's nearest: the planner
        k_late = c.corner_k_max_j if kind == "jump" else c.corner_k_max_c
        if ka > k_late or ka + max(0.0, (x0 - reach) / _sp.WALK_U) > k_max:
            return "corner late"
        if not (accepting and ground):
            return "wait"
        if self._rune_in_way(s, e, face, J_BODY_FRONT if kind == "jump" else BODY_FRONT):
            return "wait"
        self._pred = {"mode": "stop", "walk": True, "corner": True, "x_dash": round(x0, 2), "room0": round(room0, 2)}
        return None

    def _why_not_jump(self, s: dict, e: dict, ground: bool, accepting: bool, ka: int) -> str | None:
        """SP8b: the jump slam's antic. JB_CORNER first (at a wall, near), then JB_SLAM_DASH: in reach or a walk-in that
        presses by j_press_k_max (the slash phase at once), the dash-stop from j_stop_d_min (or the DashStab, j_mode 1)."""
        c = self.cfg
        if self.corner:
            wc = self._why_corner(s, e, ground, accepting, ka, "jump")
            if wc is None or wc == "wait":
                return wc
        if not self.slam_dash:
            return "off"
        if ka > c.j_k_max:
            return "late"
        if not (accepting and ground):
            return "wait"
        face, x_now, x0 = self._x_dash(s, e)
        if x_now <= 0:
            return "behind"
        if len(_sp.clappers(s)) != 1:
            return "two"                                 # one Clapper only (the person's two-Clapper rules differ)
        if self._rune_in_way(s, e, face, J_BODY_FRONT):
            return "wait"
        if x0 < c.j_stop_d_min:
            if x0 < c.j_min_u:
                return "near"                            # at its body already: the planner (its aim stance)
            if ka + max(0.0, (x0 - c.j_reach) / _sp.WALK_U) > c.j_press_k_max:
                return "walk late"
            self._pred = {"mode": "stop", "walk": True, "x_dash": round(x0, 2)}
            return None
        tm = (s.get("hero") or {}).get("tm") or {}
        if float(tm.get("dash_cd") or 0.0) > 0.02 or float(tm.get("atk_cd") or 0.0) > 0.02:
            return "wait"
        if c.j_mode == 1:
            return self._why_jstab(s, face, x0, ka)
        if x0 > c.j_stop_d_max:
            return "distance"
        p = stop_plan(x0, c, stop_u=c.j_stop_u, stop_lo=c.j_stop_lo)
        if p is None:
            return "no stop"
        if ka + p["jr"] + 3 > c.j_press_k_max:
            return "late"                                # the press after the stop would come past j_press_k_max
        self._pred = {"mode": "stop", "x_dash": round(x0, 2), **p}
        return None

    def _why_jstab(self, s: dict, face: int, x0: float, ka: int) -> str | None:
        """SP8b j_mode 1: the DashStab in the jump slam's antic - the hit before the aim, her box front outside its
        crouched body, and her x in the recoil at the aim at least j_aim_x_min (its jump aims 5 u in front of her)."""
        c = self.cfg
        if not c.d_min <= x0 <= c.d_max:
            return "distance"
        p = stab_path(x0, c, front=J_BODY_FRONT)
        if p["hit"] is None or ka + p["hit"] + HIT_LAG >= J_AIM_K:
            return "no hit"
        if p["xmin"] - HALF_W < J_BODY_FRONT + c.margin:
            return "too close"
        ja = J_AIM_K - ka
        x_aim = next((x for j, x, y in p["path"] if j == ja), p["path"][-1][1])
        if x_aim < c.j_aim_x_min:
            return "aim near"
        hx = _sp.hero_x(s)
        room = (_sp.WALL_R - hx) if face > 0 else (hx - _sp.WALL_L)
        if room < c.wall_room:
            return "wall"
        self._pred = {"mode": "stab", "x_dash": round(x0, 2), "hit": p["hit"], "xmin": round(p["xmin"], 2),
                      "land": p["land"], "top": round(p["top"], 2), "rs": False, "x_aim": round(x_aim, 2)}
        return None

    def _why_not(self, s: dict, e: dict, ground: bool, accepting: bool, ka: int) -> str | None:
        """None when a script starts now (self._pred says which); "wait" to look again next tick; else the reason it
        does not."""
        c = self.cfg
        h = s.get("hero") or {}
        if ka > max(c.k_max if self.dash_slash else -1, c.stop_k_max if self.stop else -1):
            return "late"
        if not accepting:
            return "wait"
        if not ground:
            return "wait"
        tm = h.get("tm") or {}
        if float(tm.get("dash_cd") or 0.0) > 0.02 or float(tm.get("atk_cd") or 0.0) > 0.02:
            return "wait"
        face = 1 if e.get("flipX") else -1
        cx = float(e["pos"][0])
        x0 = (_sp.hero_x(s) - cx) * face
        if x0 <= 0:
            return "behind"
        if len(_sp.clappers(s)) != 1:
            return "two"                                 # one Clapper only (the person's two-Clapper rules differ)
        hx = _sp.hero_x(s)
        front = cx + face * BODY_FRONT
        lo, hi = min(hx, front), max(hx, front)
        if any(a < hi and b > lo for a, b in self._rune_threats(int(s.get("f") or 0), s)):
            return "wait"                                # a rune circle over the way in: look again next tick
        # where she is on the dash's frame (SEND_AHEAD on: a run toward it before the start, SP8 t2 ep 0: 9.52 u at the
        # STATE, 9.19 at the dash)
        x0 += float((h.get("vel") or [0.0, 0.0])[0]) * face * SEND_AHEAD / 60.0
        why_stab = self._why_stab(s, face, x0, ka) if self.dash_slash else "off"
        if why_stab is None and not (self.stop and self.combo and not self._pred.get("rs")):
            return None
        if why_stab is None:
            # both on: the stop's two slashes before a lone DashStab (0.9 hits per antic, SP6 t6); the stab only
            # when the stop does not go
            pred = self._pred
            if self._why_stop(x0, ka) is None:
                return None
            self._pred = pred
            return None
        if self.stop:
            why_stop = self._why_stop(x0, ka)
            if why_stop is None:
                return None
            return why_stop if not self.dash_slash else why_stab
        return why_stab

    def _why_stab(self, s: dict, face: int, x0: float, ka: int) -> str | None:
        c = self.cfg
        if ka > c.k_max:
            return "late"
        if not c.d_min <= x0 <= c.d_max:
            return "distance"
        p = stab_path(x0, c)
        if p["hit"] is None:
            return "no hit"
        if p["xmin"] - HALF_W < BODY_FRONT + c.margin:
            return "too close"
        rs = self.combo and x0 >= c.combo_d_min and ka + p["hit"] + c.rs_hit_g <= c.rs_k_max
        if not rs and ka + p["land"] > AIM_K - c.land_margin:
            return "lands late"
        hx = _sp.hero_x(s)
        room = (_sp.WALL_R - hx) if face > 0 else (hx - _sp.WALL_L)   # behind her (she is on its +face side)
        if room < c.wall_room:
            return "wall"
        self._pred = {"mode": "stab", "x_dash": round(x0, 2), "hit": p["hit"], "xmin": round(p["xmin"], 2),
                      "land": p["land"], "top": round(p["top"], 2), "rs": rs}
        return None

    def _why_stop(self, x0: float, ka: int) -> str | None:
        c = self.cfg
        if ka > c.stop_k_max:
            return "late"
        if not c.stop_d_min <= x0 <= c.stop_d_max:
            return "distance"
        p = stop_plan(x0, c)
        if p is None:
            return "no stop"
        self._pred = {"mode": "stop", "x_dash": round(x0, 2), **p}
        return None
