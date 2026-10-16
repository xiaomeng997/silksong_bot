"""The person's slam strike as a fixed playbook (task 1v1 SP1, the person's decision 2026-10-16; forum.md 65).

SSBOT_FORUM_SLAM_PLAY=1 (default off: nothing here runs and every decision is the one before): when the Clapper (Song
Heavy Sentry) enters Slam Antic and the entry conditions hold, the bot plays the person's strike as a script, frame by
frame from the antic entry; otherwise (and whenever the script aborts) the rn planner decides as today.

The script (frame k counted from the antic entry, k = 0 the first STATE whose Control state reads Slam Antic; every k
is the frame the key takes effect in the game, the STATE's act.mask):
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
            press + 14: abort (the planner).
Slam 0 seen before the press was sent (a short antic or a late tick): the press at once while its frame is within
Slam 0 + press_late_max, else abort.
Entry conditions (checked on every tick until the script starts, at the latest at antic frame K_START_MAX): the hero
on the ground, accepting input, in front of the Clapper, the walk into STAND done by K_JUMP - 1 inside the arena.
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


ENABLED = _on("SSBOT_FORUM_SLAM_PLAY")
# SSBOT_FORUM_SLAM_PLAY_STANCE=<u> (default 0 = off; arm rnplay6: 6): the L2 stance while the Clapper idles / walks /
# evades: on the ground <u> in front of it, centre to centre (the person's band at the antic entry, 6.2 u; it picks the
# slam 74 % of the time at 5.4-8 u). Read by combat.tactics.gauntlet; measured separately from the strike.
STANCE_U = _num("SSBOT_FORUM_SLAM_PLAY_STANCE", 0.0)


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
    k_end: int = 110                 # the script ends here at the latest
    wall_room: float = 0.5           # the stand point at least this far inside the arena walls
    over: int = 1                    # 1: the way out after the bounce (over its body, the dash); 0: no key (SP1 it1)
    over_s0: int = 20                # the direction key from Slam 0 + this
    dash_s0: int = 23                # the dash at Slam 0 + this
    over_room: float = 6.0           # behind it only with this much room from its centre to the wall (u)

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


def control(e: dict | None) -> tuple[str | None, float]:
    for m in (e or {}).get("fsms") or ():
        if m.get("name") == "Control":
            return m.get("state"), float(m.get("t") or 0.0)
    return None, 0.0


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
    fa: int                          # the antic entry frame
    face: int                        # the Clapper's facing (+1: right)
    phase: str = "wait"              # wait (conditions not yet met) / walk / jump / air / after / done / abort
    why: str = ""
    k_start: int | None = None
    x_start: float | None = None
    k_jump: int | None = None        # the frame the jump was sent for
    x_jump: float | None = None
    k_press: int | None = None
    s0: int | None = None            # the Slam 0 entry frame (first STATE seen)
    hp0: int | None = None
    bounced: bool = False
    over_dir: int | None = None      # the way out: +1 / -1 world x, 0 none
    k_dash: int | None = None
    sent: list = field(default_factory=list)   # (frame, mask)


class SlamPlay:
    def __init__(self, cfg: PlayCfg | None = None):
        self.cfg = cfg or PlayCfg.from_env()
        self.run: Run | None = None
        self.done: list[Run] = []            # finished runs of this episode (the stats)
        self._closed_iid = None              # the Clapper whose slam was handled: no second look until it leaves it

    def reset(self) -> None:
        self.run = None
        self.done = []
        self._closed_iid = None

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
            if r.phase == "abort" or (r.phase == "wait" and r.why):
                out[f"why_{r.why}"] += 1
        return dict(out)

    def active(self) -> bool:
        return self.run is not None and self.run.phase in ("walk", "jump", "air", "after")

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
        self.run = None

    def step(self, f: int, s: dict, ground: bool, accepting: bool = True) -> int | None:
        """The mask for frame f + 2 from the STATE of frame f, or None (the planner decides)."""
        c = self.cfg
        e = clapper(s)
        st, tin = control(e)
        r = self.run
        new_antic = r is not None and st == "Slam Antic" and abs(int(f - round(tin * 60.0)) - r.fa) > 30
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
            r = self.run = Run(iid=e.get("iid"), fa=int(f - round(tin * 60.0)), face=face)
        if r.phase in ("done", "abort"):
            return None
        h = s.get("hero") or {}
        hp = int(h.get("health") or 0)
        if st == "Slam 0" and r.s0 is None:
            r.s0 = f
        k = f + SEND_AHEAD + c.lag - r.fa                  # the antic frame this tick's mask lands on
        if r.phase == "wait":
            m = self._try_start(r, k, s, e, ground, accepting, hp)
            if m is None:
                return None
            r.sent.append((f + SEND_AHEAD, m))
            return m
        if r.hp0 is not None and hp < r.hp0:
            self._close("abort", "hurt")
            return None
        cx = float(e["pos"][0])
        x = (hero_x(s) - cx) * r.face                     # in front: > 0
        if r.phase == "walk":
            if k < c.k_jump:
                m = self._walk(s, cx, r.face)
            else:
                if not ground:
                    self._close("abort", "not on the ground at the jump")
                    return None
                if not c.band[0] <= x <= c.band[1]:
                    self._close("abort", f"x {x:.2f} outside the band at the jump")
                    return None
                r.phase, r.k_jump, r.x_jump = "jump", k, round(x, 3)
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
            if c.over and r.bounced and r.s0 is not None and k - (r.s0 - r.fa) >= c.over_s0:
                if r.over_dir is None:
                    r.over_dir = self._over_dir(cx, r.face)
                if r.over_dir:
                    m |= M_R if r.over_dir > 0 else M_L
                    ks0 = k - (r.s0 - r.fa)
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

    def _press_part(self, r: Run, k: int, m: int) -> int | None:
        c = self.cfg
        if r.k_press is None:
            late = r.s0 is not None and k >= c.k_press - 3
            if k >= c.k_press or late:
                if r.s0 is not None and k - (r.s0 - r.fa) > c.press_late_max:
                    # Slam 0 seen and the frame is already past its window: the hammer comes before the slash
                    self._close("abort", "press window missed")
                    return None
                r.k_press = k
                r.phase = "after"
                return m | M_D | M_A
            if k >= c.k_down:
                m |= M_D
        return m

    def _walk(self, s: dict, cx: float, face: int) -> int:
        c = self.cfg
        h = s.get("hero") or {}
        vx = float((h.get("vel") or [0, 0])[0])
        lo, hi = c.stand
        xw = hero_x(s) + (SEND_AHEAD + c.lag) * vx / 60.0  # where she is when this mask lands (moving: still moving)
        x = (xw - cx) * face
        if lo <= x <= hi:
            return 0
        tx = cx + face * (0.5 * (lo + hi) if not lo <= x <= hi else x)
        dx = tx - xw
        if abs(dx) <= WALK_U / 2 + 0.01:
            return 0
        return M_R if dx > 0 else M_L

    def _try_start(self, r: Run, k: int, s: dict, e: dict, ground: bool, accepting: bool, hp: int) -> int | None:
        c = self.cfg
        if k > c.k_start_max:
            if not r.why:
                r.why = "late"
            r.phase = "abort"
            self._close("abort", r.why)
            return None
        cx = float(e["pos"][0])
        x = (hero_x(s) - cx) * r.face
        h = s.get("hero") or {}
        vx = float((h.get("vel") or [0, 0])[0])
        if not ground or not accepting:
            r.why = "not on the ground"
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
            r.why = "wall"
            return None
        need = abs(tgt - x) / WALK_U + abs(vx) / 8.25 * 2 + 1
        if k + need > c.k_jump - 1:
            r.why = "no time to walk"
            return None
        r.phase, r.k_start, r.x_start, r.hp0, r.why = "walk", k, round(x, 3), hp, ""
        return self._walk(s, cx, r.face)
