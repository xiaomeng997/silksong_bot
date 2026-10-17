"""Chase the Clapper's evade (task 1v1 SP8c; the person 2026-10-16, one Clapper: "when it runs away (the evade), rush up
and hit it"; forum.md 74).

SSBOT_FORUM_EVADE_CHASE=1 (read by train.forum_planner_policy; default off until its A/B; one live Clapper only - with
two the person's rule is to switch target when the focus evades, SP9): when the Clapper (Song Heavy Sentry) enters
Evade Scuttle (0.35 s = 21 game frames, 15 u/s straight back from her: 5.28 u, p10 / 90 4.98 / 5.58) the bot plays a
chase as a script until the state leaves Evade Scuttle, then the planner (and the slam playbook / the jump antic
scripts on the move that follows) decides again.

Why (forum.md 10 / 18: the Control FSM, the person's two-Clapper analysis C:\\ssbot\\data\\m2_play\\human_two): After
Scuttle reads Slam Range at once (AlertRange: the hero's body inside its centre +- 8.05 u: Close at <= 8.28 u centre to
centre, Far at >= 8.36 u, 0 of 198 off). Close Range picks SLAM / CAST (Evaded excludes EVADE), Far Range JUMP 0.5 /
CAST 0.25 / JUMP CAST 0.25. Under the v2 default she follows only ~0.2 u during the slide (in the air from her slash,
then the planner turns and even backs off: the NODASH ranking near an idle family), ends 9.1 u away (p10 / 90 8.0 /
10.1) and 162 of 260 evades of the SP6 A/B were followed by a jump move (antic_audit, sp8c evade_facts).

The script (every mask for frame f + 2; k = the evade's frame of that mask from its state time):
  run      the key toward it every frame (on the ground and in the air: her horizontal speed 8.25 u/s either way),
           none once she is nearer than stop_u (she stops dead); the end distance with the run alone
           d_end = d + (its remaining slide) - 0.1375 u per frame.
  dash     one ground dash tap (the dash key 2 frames: 3.27 u in frames 1-7 at 28 u/s, then the run) when d_end with the
           run alone is beyond dash_if_u, the dash cooldown is over, she is on the ground accepting input, the oracle's
           key filter latches toward + dash on this frame, and the dash's path keeps her at least min_u from its
           centre every frame and at least end_lo at the end (its slide stops early when its back meets the wall).
  slash    the side slash (attack 2 frames, the key toward it) when the attack is ready, she faces it, no dash /
           sprint clip (an attack from a sprint is a DashStab), and the slash from her x two frames after the mask
           meets its body box moving away.
Abort (the planner decides again): HP lost, the Clapper gone or a second one alive, the state no longer Evade Scuttle
(the normal end: "end").

    ec = EvadeChase()                                   # per episode: ec.reset()
    m = ec.step(f, s, ground, accepting, latch)         # the mask for frame f + 2, or None (the planner decides)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from ssbot.combat import slam_play as _sp


def _on(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip() == "1"


ENABLED = _on("SSBOT_FORUM_EVADE_CHASE")
CLAPPER = _sp.CLAPPER
EVADE = "Evade Scuttle"
M_L, M_R, M_A, M_DASH = _sp.M_L, _sp.M_R, _sp.M_A, _sp.M_DASH
SEND_AHEAD = _sp.SEND_AHEAD
WALK_U = _sp.WALK_U          # u per frame: her run (and her air speed with a key: SP6, 104 way-outs 0.138)
EV_F = 21                    # Evade Scuttle's frames (0.35 s; SP6 A/B 20-22)
EV_V = 0.25                  # its slide per frame (15 u/s; 5.28 u in 21 frames)
BODY_FRONT, BODY_BACK = _sp.BODY_FRONT, _sp.BODY_BACK
SLASH_X = _sp.SLASH_X
DASH_V, DASH_F = 28.0, 7     # the ground dash: u/s, the frames it moves (cast_stab: 3.27 u; live 3.36)
NO_ATK_CLIPS = ("Dash", "Sprint", "Skid")


@dataclass
class ChaseCfg:
    dash_if_u: float = 5.6       # a dash when the run alone ends farther than this (u, centre to centre)
    end_lo: float = 4.0          # ... never when it ends her nearer than this at the evade's end
    min_u: float = 3.2           # ... and never nearer than this on any frame (her box front 0.72 u off its front 2.25)
    stop_u: float = 3.6          # no key toward it nearer than this
    tap_f: int = 2               # the dash key held this many frames (a tap: the dash runs its 0.1 s on)
    dash_k_max: int = 15         # the latest evade frame (the mask's) of the dash: it moves by the slide's end, and the
    #                              dash cooldown (0.425 s) is over by the next move's antic + ~11 (SP8a / SP8b's dash
    #                              scripts in a jump antic start up to antic frame 14)
    slash_cd: int = 19           # own presses this many frames apart (the Wanderer cooldown 0.3 s = 18)
    hit_lag: int = 2             # the slash meets it this many frames after the mask's frame
    reach_spare: float = 0.1     # the slash must overlap its body box by this much
    wall_back: float = 1.34      # its back from its centre (the slide stops when it meets the wall)
    dash: int = 1                # 0: no dash (run and slash only)
    slash: int = 1               # 0: no slash


def _num_env(c: ChaseCfg) -> ChaseCfg:
    """SSBOT_FORUM_EVADE_CHASE_SET="dash_if_u=6,end_lo=4.2": trial overrides of the numbers above."""
    for kv in os.environ.get("SSBOT_FORUM_EVADE_CHASE_SET", "").replace(";", ",").split(","):
        if "=" not in kv:
            continue
        k, v = (x.strip() for x in kv.split("=", 1))
        if not hasattr(c, k):
            raise KeyError(f"SSBOT_FORUM_EVADE_CHASE_SET: unknown key {k!r}")
        cur = getattr(c, k)
        setattr(c, k, type(cur)(float(v)))
    return c


def slide_left(cx: float, face: int, n: int, back: float = 1.34) -> float:
    """Its slide still to come (u) in n frames: EV_V per frame straight back (away from its facing), cut where its back
    meets the arena wall."""
    room = (cx - _sp.WALL_L) if face > 0 else (_sp.WALL_R - cx)
    return max(0.0, min(EV_V * max(0, n), room - back))


def dash_path(d: float, n: int, slide: float) -> list[float]:
    """Her distance in front of its centre (centre to centre) on frames 1 .. DASH_F + 3 after a dash tap from d, its
    slide (slide u over the n frames left of the evade, EV_V per frame) on; the run toward it after the dash."""
    out = []
    her = 0.0
    for j in range(1, DASH_F + 4):
        her += DASH_V / 60.0 if j <= DASH_F else WALK_U
        its = min(slide, EV_V * min(j, n))
        out.append(d + its - her)
    return out


@dataclass
class Chase:
    iid: object
    face: int                   # its facing (+1 right); she is in front of it
    f0: int                     # the STATE frame of the start
    k0: int                     # the evade frame of the first mask
    x0: float                   # her x in front of its centre at the start (u)
    ground0: bool
    hp0: int
    phase: str = "run"          # run, then done / abort
    why: str = ""
    dash_k: int | None = None   # the evade frame of the dash's mask
    dash_x: float | None = None
    dash_pred: dict | None = None
    presses: list = field(default_factory=list)   # (evade frame of the mask, her x)
    hits: list = field(default_factory=list)      # (evade frame, src)
    x_end: float | None = None  # her x in front of its centre on the last Evade Scuttle tick
    k_end: int | None = None
    next_st: str | None = None  # its first state after the slide
    sent: list = field(default_factory=list)      # (f, mask) of this run's masks
    ticks: int = 0


class EvadeChase:
    def __init__(self, cfg: ChaseCfg | None = None):
        self.cfg = cfg or _num_env(ChaseCfg())
        self.run: Chase | None = None
        self.done: list[Chase] = []
        self._seen: set = set()
        self.n_evade = 0
        self.why_not: dict = {}

    def reset(self) -> None:
        self.run = None
        self.done = []
        self._seen = set()
        self.n_evade = 0
        self.why_not = {}

    def active(self) -> bool:
        return self.run is not None and self.run.phase == "run"

    def abort(self, why: str) -> None:
        if self.active():
            self._close("abort", why)

    def _close(self, phase: str, why: str = "") -> None:
        r = self.run
        if r is not None:
            r.phase, r.why = phase, r.why or why
            self.done.append(r)
        self.run = None

    def stats(self) -> dict:
        from collections import Counter
        out = Counter({"evades": self.n_evade})
        runs = self.done + ([self.run] if self.run is not None else [])
        for r in runs:
            out["runs"] += 1
            out["dash"] += r.dash_k is not None
            out["presses"] += len(r.presses)
            out["hits_in_run"] += len(r.hits)
            out[f"end_{r.phase}_{r.why}"] += 1
            if r.x_end is not None:
                out["end_close"] += r.x_end <= 8.28
        for k, v in self.why_not.items():
            out[f"no_{k}"] += v
        res = dict(out)
        res["chase_runs"] = [self._rec(r) for r in runs]
        return res

    @staticmethod
    def _rec(r: Chase) -> dict:
        return {"f0": r.f0, "k0": r.k0, "x0": r.x0, "ground0": r.ground0, "dash_k": r.dash_k, "dash_x": r.dash_x,
                "dash_pred": r.dash_pred, "presses": r.presses, "hits": r.hits, "x_end": r.x_end, "k_end": r.k_end,
                "next": r.next_st, "end": r.phase, "why": r.why, "ticks": r.ticks}

    # ---- the script ----

    def step(self, f: int, s: dict, ground: bool, accepting: bool = True, latch=None) -> int | None:
        """The mask for frame f + 2 while the chase runs, else None. latch: m -> the key mask the oracle's hold filter
        latches at f + 2 when m is sent for it (None: m itself)."""
        e = _sp.clapper(s)
        st, tin = _sp.control(e)
        h = s.get("hero") or {}
        hp = int(h.get("health") or 0)
        r = self.run
        if r is not None:
            if e is None or e.get("iid") != r.iid:
                self._close("abort", "gone")
                return None
            k = int(round(tin * 60.0)) + SEND_AHEAD
            if st != EVADE or (r.k_end is not None and k < r.k_end):
                # the slide is over (or a new one began: its own run from the next tick)
                r.next_st = st
                self._close("done", "end")
                return self.step(f, s, ground, accepting, latch) if st == EVADE else None
            if hp < r.hp0:
                self._close("abort", "hurt")
                return None
            if len(_sp.clappers(s)) != 1:
                self._close("abort", "two")
                return None
            for ev in s.get("ev") or ():
                d = ev.get("d") or {}
                if ev.get("k") == "hit" and d.get("type_key") == CLAPPER:
                    dealt = d.get("dealt", d.get("amount"))
                    if dealt is None or float(dealt) > 0:
                        r.hits.append((k - SEND_AHEAD, str(d.get("src"))))
            m = self._step_run(r, f, k, s, e, ground, accepting, latch)
            r.sent.append((f, m))
            r.ticks += 1
            return m
        if e is None or st != EVADE:
            return None
        key = (e.get("iid"), f - int(round(tin * 60.0)))
        if key in self._seen:
            return None
        self._seen.add(key)
        self.n_evade += 1
        face = 1 if e.get("flipX") else -1
        x0 = (_sp.hero_x(s) - float(e["pos"][0])) * face
        why = None
        if len(_sp.clappers(s)) != 1:
            why = "two"
        elif x0 <= 0:
            why = "behind"
        elif hp <= 0:
            why = "dead"
        if why is not None:
            self.why_not[why] = self.why_not.get(why, 0) + 1
            return None
        k = int(round(tin * 60.0)) + SEND_AHEAD
        self.run = Chase(iid=e.get("iid"), face=face, f0=f, k0=k, x0=round(x0, 3), ground0=bool(ground), hp0=hp)
        m = self._step_run(self.run, f, k, s, e, ground, accepting, latch)
        self.run.sent.append((f, m))
        self.run.ticks += 1
        return m

    def _x_mask(self, r: Chase, f: int, s: dict, e: dict) -> tuple[float, float]:
        """(her box centre's world x, its centre's world x) on the mask's frame f + 2: her velocity (or this run's own
        run keys in flight) and its velocity on."""
        h = s.get("hero") or {}
        vx = float((h.get("vel") or [0.0, 0.0])[0])
        xw = _sp.hero_x(s) + vx * SEND_AHEAD / 60.0
        ev = float((e.get("vel") or [0.0, 0.0])[0])
        cx = float(e["pos"][0]) + ev * SEND_AHEAD / 60.0
        return xw, cx

    def _step_run(self, r: Chase, f: int, k: int, s: dict, e: dict, ground: bool, accepting: bool, latch) -> int:
        c = self.cfg
        h = s.get("hero") or {}
        clip = str((h.get("anim") or {}).get("clip") or "")
        tm = h.get("tm") or {}
        xw, cx = self._x_mask(r, f, s, e)
        d = (xw - cx) * r.face                        # her x in front of its centre on the mask's frame
        r.x_end, r.k_end = round((_sp.hero_x(s) - float(e["pos"][0])) * r.face, 3), k
        toward = M_R if -r.face > 0 else M_L
        away = M_L if toward == M_R else M_R
        n = max(0, EV_F - k)                          # its slide frames still to come after the mask's frame
        slide = slide_left(cx, r.face, n, c.wall_back)
        prev = r.sent[-1][1] if r.sent else 0
        # the dash tap's second frame
        if r.dash_k is not None and k - r.dash_k < c.tap_f:
            return toward | M_DASH
        # the slash's second frame (one rising edge)
        if r.presses and k - r.presses[-1][0] == 1:
            return M_A | toward
        # a slash when it reaches its body (moving away) two frames after the mask
        if c.slash and self._slash_ok(r, k, s, e, d, cx, tm, clip, prev, away):
            r.presses.append((k, round(d, 2)))
            return M_A | toward
        # a dash when the run alone ends too far and the dash keeps clear of it
        if c.dash and r.dash_k is None and ground and accepting and k <= c.dash_k_max:
            d_run = d + slide - WALK_U * n
            if d_run > c.dash_if_u and float(tm.get("dash_cd") or 0.0) <= 0.02 and not any(
                    x in clip for x in NO_ATK_CLIPS):
                path = dash_path(d, n, slide)
                d_end = path[-1] if n >= len(path) else path[max(0, n - 1)]
                # the end: the evade's last frame (or the path's end when the evade ends later)
                if min(path) >= c.min_u and d_end >= c.end_lo and (latch is None or (
                        int(latch(toward | M_DASH)) & (M_L | M_R | M_DASH)) == toward | M_DASH):
                    r.dash_k, r.dash_x = k, round(d, 2)
                    r.dash_pred = {"d_run": round(d_run, 2), "d_end": round(d_end, 2), "min": round(min(path), 2),
                                   "n": n}
                    return toward | M_DASH
        if d - WALK_U < c.stop_u:
            return 0
        return toward

    def _slash_ok(self, r: Chase, k: int, s: dict, e: dict, d: float, cx: float, tm: dict, clip: str, prev: int,
                  away: int) -> bool:
        c = self.cfg
        if r.presses and k - r.presses[-1][0] < c.slash_cd:
            return False
        if r.dash_k is not None and k - r.dash_k < DASH_F + 2:
            return False                              # an attack from the dash / sprint is a DashStab
        if any(x in clip for x in NO_ATK_CLIPS):
            return False
        cd = tm.get("atk_cd")
        if cd is not None and float(cd) * 60.0 - (SEND_AHEAD - 1) > 0.05:
            return False
        if prev & away:
            return False                              # the slash would go the other way
        fc = (s.get("hero") or {}).get("facing")
        facing = bool(prev & (M_R if -r.face > 0 else M_L)) or (fc is not None and float(fc) * -r.face > 0)
        if not facing:
            return False
        # its body box, moved on by its slide over the mask's frame + hit_lag; her x moved on by the run
        n_h = c.hit_lag if k + c.hit_lag <= EV_F else max(0, EV_F - k)
        shift = -r.face * EV_V * n_h                  # it slides away from her (against its facing)
        span = None
        for col in e.get("colliders") or ():
            if col.get("name") == CLAPPER and col.get("enabled") and col.get("verts_world"):
                xs = col["verts_world"][0::2]
                span = (float(min(xs)) + shift, float(max(xs)) + shift)
                break
        if span is None:
            a, b = cx + shift + r.face * BODY_FRONT, cx + shift - r.face * BODY_BACK
            span = (min(a, b), max(a, b))
        xw = cx + d * r.face - r.face * WALK_U * c.hit_lag      # toward it while the slash comes out
        look = -r.face
        lo, hi = (xw + SLASH_X[0], xw + SLASH_X[1]) if look > 0 else (xw - SLASH_X[1], xw - SLASH_X[0])
        return lo < span[1] - c.reach_spare and hi > span[0] + c.reach_spare
