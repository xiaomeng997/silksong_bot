"""After the Clapper jumps, go behind it (task 1v1 SP3, the person's request of 2026-10-16, main cff3da1: "after it
jumps, go behind it, do not run far away; even with its back against the wall it moves forward a bit when it jumps,
leaving a spot behind it for Hornet to stand"; forum.md 67).

SSBOT_FORUM_JUMP_BEHIND=1 (default off: nothing here is read and every decision is the one before). During the Choir
Clapper's jump moves (CC_JUMP: Jump Antic > Jump > Air > Slam 2 > Slam Recover; CC_JUMP_CAST: Cast Slam Antic > Cast
Slam Antic 2 > Jump > Air > Slam 2 > Slam Recover, then the rune circle) the L2 stance (combat.tactics.gauntlet
_clapper_spot) is:
  antic   AIM_U in front of it (the person stands 4.2-7.7 u, p50 5.2, in front at its Jump Aim: the jump's target is the
          hero's x 5 u on its own side, so from 5 u it jumps in place and the whole flight is above her way under it);
          a hero behind it at the antic stays behind (BACK_U);
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
The wall rule (SP3 data, sp3_jumps, 1,819 jumps of the live 1v1 runs): the landing's centre was never closer than
wall_back_u (3.01 u) to the wall on its back side (p1 4.42, p5 5.43 u); with its back at the wall at take-off (0.0-1.4 u
of gap) it lands 3.5-6.0 u from it (the arc meets the wall-top ledge: it lands 2-13 frames early and is pushed out; the
person: "it moves forward a bit, leaving a spot"). Behind needs min_back_u + wall_pad_u from the landing to the wall.
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


ENABLED = _on("SSBOT_FORUM_JUMP_BEHIND")

NUM = {
    "aim_u": 5.5,          # antic: the stance in front (centre to centre, u; 0.5 u past the jump's 5 u: it jumps
    #                        slightly toward her, away from a wall behind it)
    "back_u": 3.5,         # flight / landed / rune hold: the stance behind the landing (centre to centre, u)
    "min_back_u": 3.1,     # behind needs the stance at least this far behind the landing centre (the planner keeps
    #                        turn_u 2.3 + its margin 0.5 + the hero's half width 0.25 from it), else the old back-off
    "wall_back_u": 3.0,    # the wall rule (module docstring): no landing closer to the wall behind it
    "wall_pad_u": 0.5,     # the stance at least this far from a wall (the hero's half width 0.25 + 0.25)
    "turn_u": 2.3,         # the planner's estimate: from the landing on, its standing body of either facing reaches
    #                        this far on both sides (attack_range._jb_turn_mask; the turned Idle body's back p1 2.25 u)
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


def landing(x: float, hx: float, front: float, cfg: dict | None = None) -> float:
    """The jump's landing x from its take-off x, the hero's x at its Jump Aim and its facing (+1 right), with the wall
    rule (module docstring)."""
    c = CFG if cfg is None else cfg
    land = x + 0.916 * max(-12.0, min(12.0, hx - 5.0 * front - x))
    if front > 0:
        land = max(land, WALL_L + c["wall_back_u"])
    else:
        land = min(land, WALL_R - c["wall_back_u"])
    return land


def landing_v(x0: float, vx: float, front: float, cfg: dict | None = None) -> float:
    """The landing from the take-off x and the decided vx (the first Air frame's; attack_range's jump_rule), with the
    wall rule."""
    c = CFG if cfg is None else cfg
    land = x0 + 0.916 * float(vx)
    if front > 0:
        land = max(land, WALL_L + c["wall_back_u"])
    else:
        land = min(land, WALL_R - c["wall_back_u"])
    return land


def behind_spot(land: float, front: float, cfg: dict | None = None) -> float | None:
    """BACK_U behind the landing, inside the walls by wall_pad_u; None when that leaves less than min_back_u."""
    c = CFG if cfg is None else cfg
    x = land - front * c["back_u"]
    x = min(max(x, WALL_L + c["wall_pad_u"]), WALL_R - c["wall_pad_u"])
    if (land - x) * front < c["min_back_u"]:
        return None
    return x


def aim_spot(x: float, front: float, cfg: dict | None = None) -> float:
    c = CFG if cfg is None else cfg
    v = x + front * c["aim_u"]
    return min(max(v, WALL_L + c["wall_pad_u"]), WALL_R - c["wall_pad_u"])
