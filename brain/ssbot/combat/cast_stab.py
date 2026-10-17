"""The Wanderer dash slash (DashStab) in the jump cast's antic (task 1v1 SP6, the person 2026-10-16: "if she is too far
to slash during the big rune's antic, try the dash slash"; forum.md 70), and SP8's two answers to "the two jump moves
mostly start their antic far away; try either dash slash x2 or dash then stop and side slash x2" (forum.md 72).

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
`stab_path`; SP8 calibrated on SP6 t6's 9 live stabs, C:\\ssbot\\data\\m2_dash_slash\\combo\\model_calib_bot.txt): the
dash 28 u/s on frames 1-7 after the dash's mask (3.27 u; live 3.36); the stab's clip from frame 8, vx 26.9 for 5 frames
then 17.5; its collider (0 .. 3.10 u in front of her transform, the side slash's reach) active from 7 to 14 frames after
the stab starts (live: hits at frame 15-16 after the dash's mask; SP6's model put them one frame early); its body front
in the cast antic 1.873 u from its centre (SP6 used the Idle box's 2.25: the audit's recorded collider, antic_audit);
on a hit 2 frames still, then the recoil: vx 30 u/s away, vy +20, x0.85 per frame for 20 frames (0.333 s: ~3.2 u back,
~2.1 u up), control back 0.344-0.48 s after the press, then the fall at 60 u/s^2 (1.2 u/s per 50 Hz physics step;
kinematics.py; SP6 used 72). An enemy in an antic cannot block (the person; the Clapper has no guard), so only the hit
branch is modelled: the start needs the predicted hit, her box front never nearer than its body front + STAB_MARGIN
during the lunge, and her landing by the Jump Aim (+55) minus LAND_MARGIN frames. A miss (the stab not seen to hit by
the window's end) lunges ~4.4 u on and hands back to the planner.

SSBOT_FORUM_JB_DASH_COMBO=1 (SP8 T1, default off, only with JB_DASH_SLASH; C:\\ssbot\\data\\m2_dash_slash\\combo\\
answer.txt section 4): after the DashStab's hit the Wanderer RecoilStab (RS: a hover, then a lunge 45 u/s forward and 15
down) - a NEW attack press after the hit (holding it from the stab never triggers it), read from W Recoil Cancelable
(the earliest RS start g15 game frames after the hit): no key from the hit to the press, the attack on g16-17 (the
mask's game frame; held 2 frames: one rising edge), then no key - no dash (an air dash would cancel it), no jump, no
direction - until the RS hits (src RecoilStab, ~g24-26) or its clip ends. Only when the dash starts >= combo_d_min
(10.0 u: the RS hit 0.67 u outside its body at the latest collider frame) and the RS hit is predicted by antic frame
rs_k_max (52; the Jump Aim at 55): this replaces the stab's landing rule (with the RS she lands ~aim + 33). The RS
bounces her (vy -10, then +17.4; no i-frames; the air dash refreshed): no key until the Jump Aim + post_aim_f (its body
rises in place: 0.85 u above the floor at the aim, 2.93 at +3, 5.72 at +9), then the planner (JUMP_BEHIND). The game
clock (Stamp.t_game_s) counts g: a crit's hit-stop freezes 0.2 s.

SSBOT_FORUM_JB_DASH_STOP=1 (SP8 T2, default off; the person's second option): from stop_d_min .. stop_d_max in front,
the dash + the key toward it held, both released so she stops in slash reach (centre to centre <= stop_u): a tap (the
dash's own 3.3 u) when that reaches, else the dash held into the ground sprint and released, closed loop on her x and
speed, inside Sprint Grace (the FSM: a release within 0.3 s of the sprint's start regains control at once, no skid;
fitted 0.183-0.283 s: the release by grace_f frames into the sprint); then side slashes every slash_cd frames, the
first with no direction key (she faces it), later ones with the key toward it on the frame before, walking in to
stop_stand between them (each hit knocks it ~0.48 u away), until the antic frame press_k_max.

    cs = CastStab()                                   # per episode: cs.reset()
    m = cs.step(f, s, ground, accepting, t_game)      # the mask for frame f + 2, or None (the planner decides)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from ssbot.combat import slam_play as _sp


def _on(name: str) -> bool:
    return os.environ.get(name, "0").strip() == "1"


DASH_SLASH = _on("SSBOT_FORUM_JB_DASH_SLASH")
COMBO = DASH_SLASH and _on("SSBOT_FORUM_JB_DASH_COMBO")
STOP = _on("SSBOT_FORUM_JB_DASH_STOP")
ENABLED = DASH_SLASH or STOP
CLAPPER = _sp.CLAPPER
ANTIC = ("Cast Slam Antic", "Cast Slam Antic 2")
M_L, M_R, M_A, M_DASH = _sp.M_L, _sp.M_R, _sp.M_A, _sp.M_DASH
SEND_AHEAD = _sp.SEND_AHEAD
BODY_FRONT = 1.873           # its body box front edge from its centre in the cast antic (u; Idle 2.25)
HALF_W = 0.23                # the hero's box half width
STAB_REACH = 3.10            # the DashStab polygon's reach in front of her transform
DASH_V, DASH_F = 28.0, 7     # the ground dash: u/s, the frames it moves (1 .. 7 after the dash's mask)
STAB_V0, STAB_V0_F, STAB_V = 26.9, 5, 17.5   # the stab's lunge straight from the dash, then the sprint speed
STAB_START = 8               # the stab clip's first frame after the dash's mask (the first sprint frame)
STAB_ON, STAB_OFF = 7, 14    # its collider active these frames after the stab starts
HIT_WAIT = 2                 # frames between the hit and the recoil
REC_VX, REC_VY, REC_DEC, REC_F = 30.0, 20.0, 0.85, 20
GRAV = 60.0                  # u/s^2 (kinematics: 60 x gravityScale 1; 1.2 u/s per 50 Hz physics step)
AIM_K = 55                   # the Jump Aim, frames from the antic start
SPRINT_V, SPRINT_DEC = 20.0, 1.1 * 50.0 / 60.0   # Ground Sprint: Sprint Speed Regular 20, AccelerateToX 1.1 / step
RS_CLIP = "Wanderer RecoilStab"
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
    rs_g_late: int = 24          # ... the press may still come up to here when ticks were skipped
    rs_hit_g: int = 25           # the predicted RS hit after the DashStab hit (start g15-16, collider r8-10)
    rs_k_max: int = 52           # the RS hit by this antic frame (the Jump Aim at 55)
    rs_wait_g: int = 30          # no RS clip by here: no RS (hand back)
    rs_end_g: int = 45           # the RS clip running past here: hand back
    post_aim_f: int = 10         # after the RS hit no key until the Jump Aim + this
    # SP8 T2 (JB_DASH_STOP): dash, stop, side slashes
    stop_d_min: float = 6.7      # the start's distance band (u, centre to centre; below it a tap overshoots)
    stop_d_max: float = 11.3     # ... above it the release falls past grace_f
    stop_k_max: int = 14         # the latest antic frame (the mask's) at which the stop script may start
    stop_u: float = 4.4          # the target stop (centre to centre; the standing reach in the antic 4.89)
    stop_lo: float = 3.4         # no start when the predicted stop is nearer (her box front 1.3 u off its body)
    tap_f: int = 2               # a tap: the dash held this many frames (the dash runs its 0.1 s on)
    tap_room: float = 0.35       # a tap when the dash's own travel stops her within stop_u + this
    grace_f: int = 10            # the release at most this many frames into the ground sprint (0.167 s < 0.183)
    release_lag: float = 3.0     # her travel frames from the STATE to the stop (SEND_AHEAD + the release frame)
    slash_cd: int = 19           # own presses this many frames apart (the Wanderer cooldown 0.3 s = 18)
    stop_reach: float = 4.75     # a press only from here or nearer (centre to centre)
    stop_stand: float = 4.3      # between presses walk in to here ...
    stop_min_u: float = 3.4      # ... never nearer
    press_k_max: int = 50        # the last press's antic frame (the mask's)


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


def stab_path(x0: float, cfg: StabCfg | None = None) -> dict:
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


def sprint_travel(j: int) -> float:
    """Her travel (u) by frame j after a dash's mask with the dash held all the way: the dash (frames 1 .. DASH_F at
    28 u/s), then the ground sprint slowing from 28 toward SPRINT_V by AccelerateToX's 1.1 u/s per physics step."""
    d, v = 0.0, DASH_V
    for jj in range(1, j + 1):
        if jj > DASH_F:
            v = max(SPRINT_V, v - SPRINT_DEC)
        d += v / 60.0
    return d


def stop_plan(x0: float, cfg: StabCfg) -> dict | None:
    """T2: how she stops in reach from x0 (centre to centre): a tap (the dash's own travel) or the dash held to the
    frame jr (the first frame without it) - None when neither stops her inside [stop_lo, stop_u + tap_room] in time."""
    c = cfg
    x_tap = x0 - sprint_travel(DASH_F)
    if c.stop_lo <= x_tap <= c.stop_u + c.tap_room:
        return {"tap": True, "jr": c.tap_f, "x_stop": round(x_tap, 2)}
    if x_tap < c.stop_lo:
        return None
    for jr in range(DASH_F + 1, DASH_F + c.grace_f + 1):
        x_stop = x0 - sprint_travel(jr + 1)        # she moves on through the release's own frame
        if x_stop <= c.stop_u:
            return {"tap": False, "jr": jr, "x_stop": round(x_stop, 2)} if x_stop >= c.stop_lo else None
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
    t_aim: float | None = None
    rel_j: int | None = None    # T2: the release frame (j)
    x_stop: float | None = None
    presses: list = field(default_factory=list)   # antic frames of own presses (the mask's)
    last_m: int = 0
    hits: list = field(default_factory=list)      # (antic frame, src) of landed hits while it ran
    skid: bool = False
    stab_in_stop: bool = False
    at_aim: dict | None = None


class CastStab:
    def __init__(self, cfg: StabCfg | None = None, dash_slash: bool | None = None, combo: bool | None = None,
                 stop: bool | None = None):
        self.cfg = cfg or _num_env(StabCfg())
        self.dash_slash = DASH_SLASH if dash_slash is None else dash_slash
        self.combo = (COMBO if combo is None else combo) and self.dash_slash
        self.stop = STOP if stop is None else stop
        if dash_slash is None and stop is None and not (self.dash_slash or self.stop):
            self.dash_slash = True               # constructed directly (tests, probes): the SP6 dash slash
        self.run: Stab | None = None
        self.done: list[Stab] = []
        self._seen: set = set()            # (iid, antic entry frame) looked at
        self.n_antic = 0
        self.why_not: dict = {}
        self._pred: dict = {}

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
            out["stabs" if r.mode == "stab" else "stops"] += 1
            if r.mode == "stab":
                out["hit"] += r.hit_f is not None
                out["rs_planned"] += r.rs
                out["rs_started"] += r.rs_start_g is not None
                out["rs_hit"] += r.rs_hit_g is not None
            else:
                out["stop_presses"] += len(r.presses)
                out["stop_skid"] += r.skid
                out["stop_stab"] += r.stab_in_stop
            out["hits_in_script"] += len(r.hits)
            out[f"end_{r.phase}"] += 1
            if r.why:
                out[f"why_{r.why}"] += 1
        for k, v in self.why_not.items():
            out[f"no_{k}"] += v
        res = dict(out)
        if self.combo or self.stop:
            res["runs"] = [self._rec(r) for r in self.done + ([self.run] if self.run is not None else [])]
        return res

    @staticmethod
    def _rec(r: Stab) -> dict:
        return {"mode": r.mode, "f0": r.j0 - SEND_AHEAD, "k0": r.k0, "x0": r.x0, "rs": r.rs, "k_hit": r.k_hit,
                "rs_start_g": r.rs_start_g,
                "rs_hit_g": r.rs_hit_g, "rel_j": r.rel_j, "x_stop": r.x_stop, "presses": r.presses, "hits": r.hits,
                "skid": r.skid, "stab_in_stop": r.stab_in_stop, "end": r.phase, "why": r.why, "at_aim": r.at_aim,
                "pred": r.pred}

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

    def step(self, f: int, s: dict, ground: bool, accepting: bool = True, t_game: float | None = None
             ) -> int | None:
        """The mask for frame f + 2 while a script runs, else None. t_game: the game clock (s; Stamp.t_game_s, still
        through hit-stop freezes); None: f / 60 (tests)."""
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
            if r.t_aim is None and st not in ANTIC:
                r.t_aim = t - (tin if st in ("Cast Jump", "Jump Aim") else 0.0)
                b = h.get("box")
                if b:
                    r.at_aim = {"x": round((_sp.hero_x(s) - float(e["pos"][0])) * r.face, 2),
                                "feet": round(float(b[1]) - 3.015, 2), "clip": str((h.get("anim") or {}).get("clip"))}
            m = self._step_stop(r, f, t, s, e, st, ground, accepting) if r.mode == "stop" else \
                self._step_stab(r, f, t, s, e, st, ground)
            if m is not None:
                r.last_m = m
            return m
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
        p = self._pred
        mode = p.get("mode", "stab")
        self.run = Stab(iid=e.get("iid"), face=face, j0=f + SEND_AHEAD, k0=ka, x0=round(x0, 3), pred=p, hp0=hp,
                        mode=mode, ta=t - tin, rs=bool(p.get("rs")), phase="lunge" if mode == "stab" else "dash")
        toward = M_R if -face > 0 else M_L
        self.run.last_m = toward | M_DASH
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
                # SP6: no key until her control returns (the recoil clip over), then the planner
                if (f - r.hit_f >= 8 and "Recoil" not in clip) or landed or j > c.end_j:
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
                if r.rs_sent < c.hold_a and c.rs_g0 <= gm and (r.rs_sent > 0 or gm <= c.rs_g_late):
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
                self._close("done", "post")
                return None
            if st is not None and st not in ANTIC and st not in ("Cast Jump", "Jump Aim", "Jump", "Air"):
                self._close("done", "post")
                return None
            return 0
        return None

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
            # closed loop: release when her travel through the mask's frame and the release frame ends at stop_u
            if j > DASH_F and (xr - c.release_lag * v / 60.0 <= c.stop_u or j > DASH_F + c.grace_f):
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
            if st not in ANTIC or km > c.press_k_max + 2:
                self._close("done", "aim" if st not in ANTIC else "end")
                return None
            last = r.presses[-1] if r.presses else None
            if last is not None and km - last < 1.5:
                return M_A | (toward if len(r.presses) > 1 else 0)     # the press's second frame
            cd = float(((h.get("tm") or {}).get("atk_cd")) or 0.0) * 60.0 - (SEND_AHEAD - 1)
            ready = (last is None or km - last >= c.slash_cd) and cd <= 0.05 and accepting and ground
            v = float((h.get("vel") or [0.0, 0.0])[0]) * r.face
            x_m = xr + v * SEND_AHEAD / 60.0              # her x at the mask's frame (her own velocity)
            in_reach = x_m <= c.stop_reach and km <= c.press_k_max
            if ready and in_reach:
                if not r.presses:
                    r.presses.append(round(km, 1))
                    return M_A                            # the first press: no key (she faces it from the dash)
                if r.last_m & toward:
                    r.presses.append(round(km, 1))
                    return M_A | toward
                return toward                             # the frame before the press: toward it
            if x_m - _sp.WALK_U >= c.stop_stand and x_m - _sp.WALK_U >= c.stop_min_u:
                return toward                             # walk in between presses
            return 0
        return None

    # ---- the start ----

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
        why_stab = self._why_stab(s, face, x0, ka) if self.dash_slash else "off"
        if why_stab is None:
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
        self._pred = {"mode": "stab", "hit": p["hit"], "xmin": round(p["xmin"], 2), "land": p["land"],
                      "top": round(p["top"], 2), "rs": rs}
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
        self._pred = {"mode": "stop", **p}
        return None
