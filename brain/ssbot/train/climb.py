"""Climbing the Forum's left wall to its top (the person's pocket for the finale, forum.md §10) with Wall Scramble:
hold toward the wall and press dash while on it (M2.md 2026-10-03, the person: "按住贴墙方向键再按冲刺", not wall
jumps; movement_kinematics.md §1.4b).

Mechanics (hornet_wall_scramble, movement_kinematics §1.4b): on the wall (wall slide, or a cling with Ascendant's
Grip) with Cling Grip and the direction toward the wall held, a dash press is not a dash but a scramble: Scramble
Antic (velocity 0, gravity off) -> Start Scramble (vy 22) -> Scramble Up (a downward force each physics step, 72, or
48 while dash stays held) until vy < 0.5 -> Scramble End -> back on the wall. One climb rises about 3.4 u (about 5.0 u
with dash held). Another dash press (released first, the wall direction still held) climbs again, also during
Scramble Up. At the top the roof check (Hit Roof) ends the climb and Detach moves the hero 0.2 u off the wall; holding
toward the wall grabs it again. The pocket is the highest still cling: transform y 13.45-13.60 at x 14.27 (forum.md
§8.1, §10).

WallClimber is a per-frame controller (hold times in game seconds via the STATE dt, so it works at any time scale):
APPROACH (run to the wall, jump at it) -> CLIMB (hold toward the wall; dash held for a climb, released between
climbs) -> TOP (cling at the top: hold toward the wall, nothing else). A fall to the floor goes back to APPROACH.
"""
import math
import random
import time

from ssbot.ipc.framing import mask

L, R, J, D = mask("left"), mask("right"), mask("jump"), mask("dash")
LEFT_WALL_X = 14.01        # the arena's left wall face (gate + Wall Collider, forum.md §8.1)
CLING_X = 14.27            # hero transform x when touching it
TOP_Y = 13.3               # transform y counted as "at the top" (highest still cling 13.45-13.60)
JUMP_FROM_U = 2.6          # jump at the wall from this far (hero centre to the wall face)


def _frames(s: dict, sec: float) -> int:
    dt = float(s.get("dt") or 1.0 / 60.0) or 1.0 / 60.0
    return max(2, math.ceil(sec / dt))


class WallClimber:
    def __init__(self, rng: random.Random | None = None, hold_dash: bool = True):
        self.r = rng or random.Random(0)
        self.hold_dash = hold_dash
        self.reset()

    def reset(self) -> None:
        self.phase = "APPROACH"
        self.jump_left = 0
        self.dash_left = 0
        self.dash_rest = 0
        self.scrambles = 0
        self.jumps = 0
        self.top_frames = 0
        self.frames = 0

    def act(self, s: dict, cs: dict) -> int:
        """This frame's mask; cs = the hero's cState bools by name."""
        self.frames += 1
        h = s.get("hero") or {}
        x, y = h["pos"][0], h["pos"][1]
        on_wall = bool(cs.get("wallSliding") or cs.get("wallClinging") or cs.get("wallScrambling"))
        grounded = bool(cs.get("onGround"))
        m = L
        if self.jump_left > 0:
            self.jump_left -= 1
            m |= J
        if self.phase == "TOP" and not (on_wall and y >= TOP_Y - 0.15):
            self.phase = "CLIMB" if on_wall else "APPROACH"
        if self.phase == "APPROACH":
            if on_wall:
                self.phase = "CLIMB"
            elif grounded and x - LEFT_WALL_X < JUMP_FROM_U and self.jump_left == 0:
                self.jump_left = _frames(s, 0.30)
                self.jumps += 1
                m |= J
        if self.phase == "CLIMB":
            if grounded and not on_wall:
                self.phase = "APPROACH"
            elif on_wall and y >= TOP_Y and cs.get("wallClinging") and not cs.get("wallScrambling"):
                self.phase = "TOP"
            elif on_wall or cs.get("wallScrambling"):
                if self.dash_left > 0:
                    self.dash_left -= 1
                    m |= D
                    if self.dash_left == 0:
                        self.dash_rest = 2
                elif self.dash_rest > 0:
                    self.dash_rest -= 1
                else:
                    # a new climb: from the wall, or during Scramble Up once it slows (keeps the climb going)
                    vy = (h.get("vel") or [0.0, 0.0])[1]
                    if not cs.get("wallScrambling") or vy < 4.0:
                        self.dash_left = _frames(s, 0.25) if self.hold_dash else 2
                        self.scrambles += 1
                        m |= D
        if self.phase == "TOP":
            self.top_frames += 1
        return m


class ClimbProbe:
    """Repeated climbs in the running battle: from a random x on the floor (walk there first), climb, stay at the top
    for a moment, drop off, again. A try succeeds when the hero clings at y >= TOP_Y within --timeout game seconds of
    its start; per try: game seconds to the top, scramble presses, jumps, hits taken."""

    def __init__(self, cstate_names: list[str], rng: random.Random):
        self.names = cstate_names
        self.r = rng

    def _cs(self, s: dict) -> dict:
        from ssbot.tools.cstate import decode
        try:
            return decode(s["hero"]["cstate"], self.names)
        except (KeyError, ValueError, TypeError):
            return {}

    def run(self, link, tap, tries: int, timeout_s: float = 8.0, hold_dash: bool = True) -> dict:
        rows = []
        last = link.frame
        for k in range(tries):
            start_x = self.r.uniform(17.0, 30.0)
            # walk to the start x (either side), keys up for a moment
            t_end = time.monotonic() + 15.0
            while time.monotonic() < t_end:
                s = link.wait_state(newer_than=last, timeout_s=3.0)
                last = s["f"]
                x = s["hero"]["pos"][0]
                cs = self._cs(s)
                if abs(x - start_x) < 0.5 and cs.get("onGround"):
                    break
                link.act(last + 2, (R if x < start_x else L) if not (cs.get("wallClinging") or cs.get("wallSliding"))
                         else R | J, hold_frames=0)
            climber = WallClimber(self.r, hold_dash=hold_dash)
            hits0 = len(tap.damage)
            g = 0.0
            row = {"try": k, "start_x": round(start_x, 2), "ok": False}
            y_max = 0.0
            while g < timeout_s:
                s = link.wait_state(newer_than=last, timeout_s=3.0)
                last = s["f"]
                g += float(s.get("dt") or 0.0)
                cs = self._cs(s)
                y_max = max(y_max, s["hero"]["pos"][1])
                link.act(last + 2, climber.act(s, cs), hold_frames=0)
                if climber.phase == "TOP" and climber.top_frames >= 10:
                    row.update(ok=True, t_top=round(g, 3), y=round(s["hero"]["pos"][1], 3),
                               x=round(s["hero"]["pos"][0], 3))
                    break
            row.update(scrambles=climber.scrambles, jumps=climber.jumps, y_max=round(y_max, 3),
                       hits=len(tap.damage) - hits0, game_s=round(g, 3))
            rows.append(row)
            print(f"climb {k}: {row}", flush=True)
            # stay a moment, then drop off the wall
            for _ in range(_frames(link.state or {}, 0.5)):
                s = link.wait_state(newer_than=last, timeout_s=3.0)
                last = s["f"]
                link.act(last + 2, L, hold_frames=0)
            for _ in range(_frames(link.state or {}, 0.3)):
                s = link.wait_state(newer_than=last, timeout_s=3.0)
                last = s["f"]
                link.act(last + 2, R, hold_frames=0)
        ok = [r for r in rows if r["ok"]]
        t = sorted(r["t_top"] for r in ok)
        return {"tries": len(rows), "ok": len(ok), "rate": round(len(ok) / max(1, len(rows)), 3),
                "t_top_p50": t[len(t) // 2] if t else None, "t_top_max": t[-1] if t else None,
                "fails": [r for r in rows if not r["ok"]], "rows": rows}
