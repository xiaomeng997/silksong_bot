"""After the Clapper jumps, go behind it (task 1v1 SP3, the person's request of 2026-10-16, main cff3da1: "after it
jumps, go behind it, do not run far away; even with its back against the wall it moves forward a bit when it jumps,
leaving a spot behind it for Hornet to stand"; forum.md 67).

SSBOT_FORUM_JUMP_BEHIND=1 (default since 2026-10-16: on with SSBOT_FORUM_V2=1, off without v2; =0 off, every decision the one before). During the Choir
Clapper's jump moves (CC_JUMP: Jump Antic > Jump > Air > Slam 2 > Slam Recover; CC_JUMP_CAST: Cast Slam Antic > Cast
Slam Antic 2 > Jump > Air > Slam 2 > Slam Recover, then the rune circle) the L2 stance (combat.tactics.gauntlet
_clapper_spot) is:
  antic   AIM_U in front of it (the person stands 4.2-7.7 u, p50 5.2, in front at its Jump Aim: the jump's target is the
          hero's x 5 u on its own side, so from 5 u it jumps in place and the whole flight is above her way under it);
          aim_wall_u (7 u) when its back is within push_from_u of a wall (it then jumps 1.8 u toward her, away from
          the wall: from 5-6 u it landed as near as 3.35 u to the wall, the A/B's one jump hit); a hero behind it at
          the antic stays behind (BACK_U);
  flight  BACK_U behind the landing (the person: 3.0-5.1 u, p50 3.7, at the landing; the slash reaches its back edge,
          1.27-1.34 u behind its centre, from up to about 4.4 u; its body turning at Idle reaches 2.25 u behind the old
          back side: below), the landing = take-off + 0.916 vx (vx: the first Air frame's; before it the hero's x on
          the first tick past the antic: target = hero x - 5 x facing, vx = clamp(target - x, +-12); forum.md 33.2, p50
          error 0.03 u off the walls) with the wall rule below, and never short of where it is now along the jump; on
          Slam 2 the Clapper's own x;
  landed  the same spot through Slam 2 / Slam Recover, the hit weight on (slash its back);
  after   a jump cast's rune circle (6.48 u in front of the landing, r 7.19: from 0.71 u behind it) bursts 65-73 frames
          after the landing, 45-53 frames after the move ends: the stance stays BACK_U behind the landing until then
          (gauntlet's rune hold, BACK_U instead of behind_land_u 2.5 u, which a turning body reaches).
The wall rule (SP3 data, sp3_jumps, 1,839 jumps of the live 1v1 runs): the landing's centre was never closer than
wall_back_u (3.01 u) to the wall on its back side (p1 4.42, p5 5.43 u). Taking off with its centre within push_from_u (4 u)
of the wall behind it (its back 0-2.7 u from the wall), it landed 3.47 u from it once and otherwise >= 3.83 u (p5
4.58; 334 jumps): when the formula puts it nearer, the arc meets the wall-top ledge, it lands 2-13 frames early and is
pushed out (the person: "it moves forward a bit, leaving a spot"); the 3.0-3.4 u landings took off 4.6-5.4 u out and
jumped back (the hero within 5 u at its Jump Aim). Behind needs min_back_u + wall_pad_u from the landing to the wall.
The turn: a landed jump ends in Idle, which turns the Clapper to a hero behind it, so its front (2.25 u) reaches her side
(S2 live, 304 jumps with the hero behind the landing: 17 body hits at Idle 2.0-2.5 u behind it). The planner's estimate
(attack_range.RangeTracker.estimate) adds its standing body of either facing (turn_u) from the landing (Slam 2 / Slam
Recover) on, so a stance or a slash from behind keeps turn_u + the margin from its centre.
The Clapper's corner (forum_v2.corner_zones, rows ending between a Clapper and a wall closer than 13 u rank last) does
not count a Clapper in a jump move: its back side is the spot.
The slam that may come next with the hero between it and a wall (combat.slam_play): when the playbook's stand point does
not fit inside the arena, a nearer one (>= NEAR_STAND_U; SP1's pinned trials: 3.6-7.25 u at the jump all succeeded).

SSBOT_FORUM_JUMP_BEHIND_SET="aim_u=5,back_u=3.5": trial overrides of the numbers below.
"""
from __future__ import annotations

import os

CLAPPER = "Song Heavy Sentry"
WALL_L, WALL_R = 14.01, 48.99          # ssbot.core.forum (the import firewall keeps combat light)
JUMP_FAMS = ("CC_JUMP", "CC_JUMP_CAST")
ANTIC_STATES = ("Jump Antic", "Cast Slam Antic", "Cast Slam Antic 2", "Cast Jump", "Jump Aim")
AIR_STATES = ("Jump", "Air")
LANDED_STATES = ("Charged?", "Slam Effects?", "Slam 2", "Slam Recover")


def _on(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip() == "1"


# The person, 2026-10-16: the faster arm is the default (SP3: rnjb kill p50 24.9 s vs rnplay 33.4 s, +0.17 landed
# hits/s). Unset, SSBOT_FORUM_JUMP_BEHIND follows SSBOT_FORUM_V2 (on with v2, off without it); 0 turns it off
# (arm rnplay0 = rnplay without it).
ENABLED = _on("SSBOT_FORUM_JUMP_BEHIND", "1" if _on("SSBOT_FORUM_V2") else "0")

# SP4 (task 1v1 SP4, the person's notes of 2026-10-16 while SP3 ran; forum.md 68): sub-switches of JUMP_BEHIND, each
# on by default with v2 since the SP4 A/B (only with ENABLED); =0 off, every decision the SP3 one.
#   SSBOT_FORUM_JB_PASS        the flight's hits count when pressed on the ground ("slash while running past it":
#                              GoalPrefs.ground_hit instead of no_hit in the flight branch; passing under is a dash, so
#                              no up slash is rewarded there - the hits from the ground near its take-off / landing)
#   SSBOT_FORUM_JB_LAND        from behind, its falling body counts (ground presses) from the apex on ("once it comes
#                              down near the ground you can already slash; the bot waits for its recovery")
#   SSBOT_FORUM_JB_NOJUMP      behind it from the descent to the rune hold: rows without a jump key first among equal
#                              landed hits (GoalPrefs.ground_first; "Hornet jumps once behind it and loses a hit; the
#                              ground there has no damage box"); SP4 replay: at the landing tick every ground hit row
#                              was flagged S for one tick and a JUMP(48) row (no hit) won on a lower key, then the
#                              committed jump made the next ticks' safe ground slashes not "keep"
#   SSBOT_FORUM_JB_CAST_ANTIC  the jump cast's antic (the big rune, aim at antic +55 frames): on the ground cast_u in
#                              front (in slash reach of its front edge, 2.25 u) with ground hits counting until
#                              cast_slash_s, then the aim stance ("stand in front and slash at least twice")
#   SSBOT_FORUM_JB_WALL        the planner's estimate (are_types.clapper.jump_rule) lands a jump taking off with its
#                              back within push_from_u of a wall at least wall_push_u out (the wall rule's push), so a
#                              back-off keeps clear of the pushed landing, not the vertical one (the person's hit)


def _sub(name: str) -> bool:
    # SP4 A/B (forum.md 68.5): unset, each follows SSBOT_FORUM_V2 (with JUMP_BEHIND on); =0 turns it off
    return ENABLED and _on(name, "1" if _on("SSBOT_FORUM_V2") else "0")


PASS_HIT = _sub("SSBOT_FORUM_JB_PASS")
LAND_HIT = _sub("SSBOT_FORUM_JB_LAND")
NO_JUMP = _sub("SSBOT_FORUM_JB_NOJUMP")
CAST_ANTIC = _sub("SSBOT_FORUM_JB_CAST_ANTIC")
WALL_PUSH = _sub("SSBOT_FORUM_JB_WALL")

NUM = {
    "aim_u": 5.5,          # antic: the stance in front (centre to centre, u; 0.5 u past the jump's 5 u: it jumps
    #                        slightly toward her, away from a wall behind it)
    "aim_wall_u": 7.0,     # ... with its back within push_from_u of a wall (aim_spot)
    "back_u": 3.5,         # flight / landed / rune hold: the stance behind the landing (centre to centre, u)
    "min_back_u": 3.1,     # behind needs the stance at least this far behind the landing centre (the planner keeps
    #                        turn_u 2.3 + its margin 0.5 + the hero's half width 0.25 from it), else the old back-off
    "wall_back_u": 3.0,    # the wall rule (module docstring): no landing closer to the wall behind it
    "wall_push_u": 4.4,    # ... nor closer than this when it took off with its back within push_from_u of that wall
    "push_from_u": 4.0,    #     (334 such jumps: 3.47 u once, otherwise >= 3.83, p5 4.58)
    "wall_pad_u": 0.5,     # the stance at least this far from a wall (the hero's half width 0.25 + 0.25)
    "turn_u": 2.3,         # the planner's estimate: from the landing on, its standing body of either facing reaches
    #                        this far on both sides (attack_range._jb_turn_mask; the turned Idle body's back p1 2.25 u)
    "cast_u": 4.3,         # SSBOT_FORUM_JB_CAST_ANTIC: the stance in front in its jump cast's antic (its front edge
    #                        2.25 u: a 1.8 u gap, inside the side slash's reach; it jumps 0.6 u back from there)
    "cast_slash_s": 0.62,  # ... until this long after the antic start (aim at +55 frames = 0.92 s; 1.2 u back to
    #                        aim_u takes 9 frames)
}
BODY_TOP_U = 3.92          # the standing body's top above the floor (Idle box y 3.01-6.92)


def _load() -> dict:
    d = dict(NUM)
    for kv in os.environ.get("SSBOT_FORUM_JUMP_BEHIND_SET", "").replace(";", ",").split(","):
        if "=" not in kv:
            continue
        k, v = (x.strip() for x in kv.split("=", 1))
        if k not in d:
            raise KeyError(f"SSBOT_FORUM_JUMP_BEHIND_SET: unknown key {k!r}")
        d[k] = float(v)
    return d


CFG = _load()


def wall_rule(x0: float, land: float, front: float, cfg: dict | None = None) -> float:
    """The wall rule (module docstring) on a formula landing: never closer than wall_back_u to the wall behind it, nor
    closer than wall_push_u when it took off with its back within push_from_u of that wall."""
    c = CFG if cfg is None else cfg
    room0 = (x0 - WALL_L) if front > 0 else (WALL_R - x0)
    lo = c["wall_push_u"] if room0 < c["push_from_u"] else c["wall_back_u"]
    if front > 0:
        return max(land, WALL_L + lo)
    return min(land, WALL_R - lo)


def push_l(x: float, s: int, L: float, cfg: dict | None = None) -> float:
    """SSBOT_FORUM_JB_WALL: the decided landing offset L (along the facing s) of a jump taking off with its back within
    push_from_u of a wall raised to land at least wall_push_u from that wall (the wall rule's push)."""
    c = CFG if cfg is None else cfg
    room0 = (x - WALL_L) if s > 0 else (WALL_R - x)
    if room0 < c["push_from_u"]:
        return max(float(L), c["wall_push_u"] - room0)
    return float(L)


def landing(x: float, hx: float, front: float, cfg: dict | None = None) -> float:
    """The jump's landing x from its take-off x, the hero's x at its Jump Aim and its facing (+1 right), with the wall
    rule."""
    return wall_rule(x, x + 0.916 * max(-12.0, min(12.0, hx - 5.0 * front - x)), front, cfg)


def landing_v(x0: float, vx: float, front: float, cfg: dict | None = None) -> float:
    """The landing from the take-off x and the decided vx (the first Air frame's; attack_range's jump_rule), with the
    wall rule."""
    return wall_rule(x0, x0 + 0.916 * float(vx), front, cfg)


def behind_spot(land: float, front: float, cfg: dict | None = None) -> float | None:
    """BACK_U behind the landing, inside the walls by wall_pad_u; None when that leaves less than min_back_u."""
    c = CFG if cfg is None else cfg
    x = land - front * c["back_u"]
    x = min(max(x, WALL_L + c["wall_pad_u"]), WALL_R - c["wall_pad_u"])
    if (land - x) * front < c["min_back_u"]:
        return None
    return x


def aim_spot(x: float, front: float, cfg: dict | None = None) -> float:
    """The antic stance: aim_u in front; aim_wall_u when its back is within push_from_u of a wall (from 5-6 u it jumps
    in place against the wall: landing room 3.35-3.7 u in 3 of 23; from >= 6 u it jumps toward her: >= 4.16 u, n 302)."""
    c = CFG if cfg is None else cfg
    room0 = (x - WALL_L) if front > 0 else (WALL_R - x)
    u = c["aim_wall_u"] if room0 < c["push_from_u"] else c["aim_u"]
    v = x + front * u
    return min(max(v, WALL_L + c["wall_pad_u"]), WALL_R - c["wall_pad_u"])
