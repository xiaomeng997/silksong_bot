"""The Wanderer dash slash (DashStab) in the jump cast's antic (task 1v1 SP6, the person 2026-10-16: "if she is too far
to slash during the big rune's antic, try the dash slash"; forum.md 70).

SSBOT_FORUM_JB_DASH_SLASH=1 (default off; read by train.forum_planner_policy): when the Clapper (Song Heavy Sentry)
enters the jump cast's antic (Control "Cast Slam Antic", 16 frames, then "Cast Slam Antic 2", 40 frames, Jump Aim at
+55/56; SP4 / SP5 A/B: the hero 9.2 u from its centre at the antic start (p10 / 90 6.2 / 10.3), 0.25 hits per antic)
and the hero stands on the ground in front of it beyond the side slash's reach, the bot plays the dash slash as a
script: the ground dash toward it with the dash key HELD (the sprint FSM's Dashed state goes to the sprint only while
the dash is held, and Ground Sprint skids out when it is released; t3, 79eb963: a 2-frame dash ran on as Dash To Run
and the attack was a plain slash, 8 of 8), the attack pressed on the dash's last frames (Ground Sprint reads it
queued, 0.1 s: the stab starts on the first sprint frame), the dash key and the key toward it held until the stab hits,
then no key through the recoil until her control returns; the planner decides again after that (or at once, all keys
released, when the stab is not seen to hit).

The model (C:\\ssbot\\data\\m2_dash_slash: the decompiled hornet_sprint FSM, the person's 92 Wanderer dash slashes;
`stab_path`): the dash 28 u/s for 0.1 s (2.8 u); the stab from the first sprint frame, vx 26.9 for 4 frames then 17.5;
its collider (0 .. 3.10 u in front of her transform, the side slash's reach) active from 7 to 14 frames after the stab
starts (the person's 53 hits: 7-8 frames after the press, at 2.5-6.6 u); on a hit 2 frames still, then the recoil: vx 30 u/s
away, vy +20, x0.85 per frame for 20 frames (0.333 s: ~3.2 u back, ~2.1 u up), control back 0.344-0.48 s after the
press, then the fall. An enemy in an antic cannot block (the person; the Clapper has no guard), so only the hit branch
is modelled: the start needs the predicted hit, her box front never nearer than its body front + STAB_MARGIN during
the lunge, and her landing by the Jump Aim (+55) minus LAND_MARGIN frames. A miss (the stab not seen to hit by the
window's end) lunges ~4.4 u on and hands back to the planner.

    cs = CastStab()                                   # per episode: cs.reset()
    m = cs.step(f, s, ground, accepting, t_game)      # the mask for frame f + 2, or None (the planner decides)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from ssbot.combat import slam_play as _sp

ENABLED = os.environ.get("SSBOT_FORUM_JB_DASH_SLASH", "0").strip() == "1"
CLAPPER = _sp.CLAPPER
ANTIC = ("Cast Slam Antic", "Cast Slam Antic 2")
M_L, M_R, M_A, M_DASH = _sp.M_L, _sp.M_R, _sp.M_A, _sp.M_DASH
SEND_AHEAD = _sp.SEND_AHEAD
BODY_FRONT = 2.25            # its body box front edge from its centre (u)
HALF_W = 0.23                # the hero's box half width
STAB_REACH = 3.10            # the DashStab polygon's reach in front of her transform
DASH_V, DASH_F = 28.0, 6     # the ground dash: u/s, frames
STAB_V0, STAB_V0_F, STAB_V = 26.9, 4, 17.5   # the stab's lunge straight from the dash, then the sprint speed
STAB_START = 7               # the stab's first frame after the dash press (the first sprint frame + 1)
STAB_ON, STAB_OFF = 7, 14    # its collider active these frames after the stab starts
HIT_WAIT = 2                 # frames between the hit and the recoil
REC_VX, REC_VY, REC_DEC, REC_F = 30.0, 20.0, 0.85, 20
GRAV = 72.0                  # u/s^2 (slam_play.GRAV)
AIM_K = 55                   # the Jump Aim, frames from the antic start


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


def stab_path(x0: float, cfg: StabCfg | None = None) -> dict:
    """The dash slash from x0 u in front of its centre (centre to centre), the dash on frame 0: the predicted frame of
    the hit (None: no hit), her nearest x (centre), the recoil's top height, the landing frame, and the path [(j, x,
    y)] (frames from the dash press; x in front of its centre, y above the floor)."""
    c = cfg or StabCfg()
    x, y, path = x0, 0.0, []
    for j in range(STAB_START):
        x -= (DASH_V if j < DASH_F else STAB_V0) / 60.0
        path.append((j, x, y))
    hit, xmin = None, x
    j = STAB_START
    for i in range(STAB_OFF + 1):
        x -= (STAB_V0 if i < STAB_V0_F else STAB_V) / 60.0
        xmin = min(xmin, x)
        path.append((j, x, y))
        if i >= STAB_ON and x - STAB_REACH <= BODY_FRONT:
            hit = j
            break
        j += 1
    if hit is None:
        return {"hit": None, "xmin": xmin, "path": path, "land": None, "top": 0.0}
    for _ in range(HIT_WAIT):
        j += 1                                    # the person's profiles: 17.5 on the hit frame, then -30 at once
        path.append((j, x, y))
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


@dataclass
class Stab:
    iid: object
    face: int                   # its facing (+1 right)
    j0: int                     # the STATE frame of the dash's mask (frame j = 0 is f0 + SEND_AHEAD)
    k0: int                     # the antic frame of the dash
    x0: float
    pred: dict = field(default_factory=dict)
    phase: str = "lunge"        # lunge / recoil / done / abort
    why: str = ""
    hit_f: int | None = None
    hp0: int = 0


class CastStab:
    def __init__(self, cfg: StabCfg | None = None):
        self.cfg = cfg or StabCfg()
        self.run: Stab | None = None
        self.done: list[Stab] = []
        self._seen: set = set()            # (iid, antic entry frame) looked at
        self.n_antic = 0
        self.why_not: dict = {}

    def reset(self) -> None:
        self.run = None
        self.done = []
        self._seen = set()
        self.n_antic = 0
        self.why_not = {}

    def stats(self) -> dict:
        from collections import Counter
        out = Counter({"antics": self.n_antic})
        for r in self.done + ([self.run] if self.run is not None else []):
            out["stabs"] += 1
            out["hit"] += r.hit_f is not None
            out[f"end_{r.phase}"] += 1
            if r.why:
                out[f"why_{r.why}"] += 1
        for k, v in self.why_not.items():
            out[f"no_{k}"] += v
        return dict(out)

    def active(self) -> bool:
        return self.run is not None and self.run.phase in ("lunge", "recoil")

    def abort(self, why: str) -> None:
        if self.active():
            self._close("abort", why)

    def _close(self, phase: str, why: str = "") -> None:
        r = self.run
        if r is not None:
            r.phase, r.why = phase, r.why or why
            self.done.append(r)
        self.run = None

    def step(self, f: int, s: dict, ground: bool, accepting: bool = True) -> int | None:
        c = self.cfg
        e = _sp.clapper(s)
        st, tin = _sp.control(e)
        h = s.get("hero") or {}
        hp = int(h.get("health") or 0)
        r = self.run
        if r is not None:
            j = f + SEND_AHEAD - r.j0                     # frames since the dash's mask
            if hp < r.hp0:
                self._close("abort", "hurt")
                return None
            if e is None or e.get("iid") != r.iid:
                self._close("abort", "gone")
                return None
            if r.hit_f is None and any(ev.get("k") == "hit" and (ev.get("d") or {}).get("type_key") == CLAPPER
                                       and "Dash" in str((ev.get("d") or {}).get("src")) for ev in s.get("ev") or ()):
                r.hit_f, r.phase = f, "recoil"
            if r.phase == "lunge":
                if j > c.hit_wait_max + STAB_START:
                    self._close("done", "miss")
                    return 0                                 # release the dash (a held one sprints on into it)
                toward = M_R if -r.face > 0 else M_L
                m = toward | M_DASH                          # the dash held: the sprint, the stab from it
                if c.press_j <= j < c.press_j + c.hold_a:
                    m |= M_A
                return m
            # the recoil: no key until her control returns (the recoil clip over), then the planner
            clip = str((h.get("anim") or {}).get("clip") or "")
            if (f - r.hit_f >= 8 and "Recoil" not in clip) or ground or j > c.end_j:
                self._close("done", "landed" if ground else "control")
                return None
            return 0
        # a new start?
        if e is None or st != "Cast Slam Antic":
            return None
        ka = int(round(tin * 60.0)) + SEND_AHEAD          # the antic frame the next mask lands on
        key = (e.get("iid"), f - int(round(tin * 60.0)))
        if key in self._seen:
            return None
        why = self._why_not(s, e, ground, accepting, ka)
        if why is not None:
            if why != "wait":
                self._seen.add(key)
                self.n_antic += 1
                self.why_not[why] = self.why_not.get(why, 0) + 1
            return None
        self._seen.add(key)
        self.n_antic += 1
        face = 1 if e.get("flipX") else -1
        x0 = (_sp.hero_x(s) - float(e["pos"][0])) * face
        self.run = Stab(iid=e.get("iid"), face=face, j0=f + SEND_AHEAD, k0=ka, x0=round(x0, 3),
                        pred=self._pred, hp0=hp)
        toward = M_R if -face > 0 else M_L
        return toward | M_DASH

    def _why_not(self, s: dict, e: dict, ground: bool, accepting: bool, ka: int) -> str | None:
        """None when the dash slash starts now; "wait" to look again next tick; else the reason it does not."""
        c = self.cfg
        if ka > c.k_max:
            return "late"
        h = s.get("hero") or {}
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
        if not c.d_min <= x0 <= c.d_max:
            return "distance"
        p = stab_path(x0, c)
        if p["hit"] is None:
            return "no hit"
        if p["xmin"] - HALF_W < BODY_FRONT + c.margin:
            return "too close"
        if ka + p["land"] > AIM_K - c.land_margin:
            return "lands late"
        hx = _sp.hero_x(s)
        room = (_sp.WALL_R - hx) if face > 0 else (hx - _sp.WALL_L)   # behind her (she is on its +face side)
        if room < c.wall_room:
            return "wall"
        self._pred = {"hit": p["hit"], "xmin": round(p["xmin"], 2), "land": p["land"], "top": round(p["top"], 2)}
        return None
