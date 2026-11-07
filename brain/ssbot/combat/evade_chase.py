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
           centre every frame and at least end_lo at the end (its slide stops early when its back meets the wall);
           by evade frame dash_k_max; not within atk_lock frames of her last attack press (t2, 14cb7e7: the dash key
           4-6 frames after a slash press is ignored - 0 of 8 at 4, 12 of 15 at 5-6, all 117 from 7 on; seven slides
           ended Far after a slash hit at the slide's start: her recoil and no dash); a dash not seen to start by the
           mask + 3 is tried again. In the air (air_dash): the air dash (2 frames at 28 u/s, then the Air Sprint's
           0.235 s from 26.9 u/s down by 1.1 per physics step: ~5.8 u in 16 frames; movement_kinematics 1.3) only
           when the run alone ends Far (beyond air_if_u) and its path keeps air_margin more room.
  slash    the side slash (attack 2 frames, the key toward it) from evade frame slash_k_min on (t1, 7c342fa: a hit
           early in the slide pushed her back with its recoil and it 0.48 u on - one evade ended 9.0 u away, a far
           cast), when the attack is ready, she faces it, no dash / sprint clip (an attack from a sprint is a
           DashStab), and the slash from her x two frames after the mask meets its body box moving away.
Not while a jump cast's rune circle is lit or still to come over her way to it (t1: the chase into the previous jump
cast's circle, lit 42 frames after the evade's start, 2 HP): no start, or the run hands back ("rune").
Abort (the planner decides again): HP lost, the Clapper gone or a second one alive, a rune circle over the way, the
state no longer Evade Scuttle (the normal end: "end").
SP11-0 (SSBOT_FORUM_TWO_GUARD, combat.two_play.guard_spans; step(guard=...)): with two Clappers the other one's danger
spans (its jump landing band once aimed, its big rune circle, its hammer, its body): no start and abort ("guard") with
her x inside one; the run key only while the step stays out of the nearest span on the way to the focus, the dash /
air dash only when their whole travel does (SP10c T2: 10 of 68 HP losses were the chase running her under the other
one's landing or into its body).
Two Clappers (task 1v1 SP9a S1, SSBOT_FORUM_TWO_CHASE, combat.two_play; EvadeChase(two=True)): the focus's evade (the
L2 target the policy passes, else the nearer one) is chased the same way, the slash never pressed when it would meet
the other one's body (the switch answer 2a: B is free during F's slide and decides at once when hit, 19 / 19); one
live Clapper chases only with one=True (SSBOT_FORUM_EVADE_CHASE).
The distance brake over its body (Task 179 seq 259, live w13_task182 2583-2588, 2 HP): "no key" stops her approach, but
falling in the air over its body it only holds her there: she stays over a body that slides at 0.25 u a frame and stands
up again during the slide. On such a tick the policy's move away from it, when its key latches, goes out and the run
ends (yields_brake_to). Rising, in front of the body, on the ground or with any other mask the brake stays.

    ec = EvadeChase()                                   # per episode: ec.reset()
    m = ec.step(f, s, ground, accepting, latch)         # the mask for frame f + 2, or None (the planner decides)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from ssbot.combat import cast_stab as _cs
from ssbot.combat import slam_play as _sp


def _on(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip() == "1"


# The lead's note of 2026-10-17 (the person: "a single Clapper is not dangerous - fight it however is fastest"; SP8d's
# four-arm A/B: sp8all = the low hop + EVADE_CHASE + JB_SLAM_DASH + JB_CORNER the fastest, kill p50 17.3 s, 1.305 landed / s,
# 16 / 16 HP-hitless): unset, SSBOT_FORUM_EVADE_CHASE follows SSBOT_FORUM_V2 (on with v2), =0 off (arm rnsp8bc0); one
# live Clapper only (two Clappers: SSBOT_FORUM_TWO_CHASE)
ENABLED = _on("SSBOT_FORUM_EVADE_CHASE", "1" if _on("SSBOT_FORUM_V2") else "0")
CLAPPER = _sp.CLAPPER
EVADE = "Evade Scuttle"
M_L, M_R, M_A, M_DASH = _sp.M_L, _sp.M_R, _sp.M_A, _sp.M_DASH
SEND_AHEAD = _sp.SEND_AHEAD
WALK_U = _sp.WALK_U          # u per frame: her run (and her air speed with a key: SP6, 104 way-outs 0.138)
EV_F = 21                    # Evade Scuttle's frames (0.35 s; SP6 A/B 20-22)
EV_V = 0.25                  # its slide per frame (15 u/s; 5.28 u in 21 frames)
BODY_FRONT, BODY_BACK = _sp.BODY_FRONT, _sp.BODY_BACK
BODY_TOP = 6.92              # its standing body top (the collider's; the slide crouches to 6.2 for 3 frames, then stands)
SLASH_X = _sp.SLASH_X
DASH_V, DASH_F = 28.0, 7     # the ground dash: u/s, the frames it moves (cast_stab: 3.27 u; live 3.36)
NO_ATK_CLIPS = ("Dash", "Sprint", "Skid")
AIR_DASH_F = 2               # the air dash: 2 physics steps at 28 u/s (0.04 s), then the Air Sprint
AIR_SPRINT_F, AIR_SPRINT_V0, AIR_SPRINT_DEC = 14, 26.9, 1.1 * 50.0 / 60.0   # 0.235 s from 26.9 u/s, -1.1 per step


@dataclass
class ChaseCfg:
    dash_if_u: float = 5.6       # a dash when the run alone ends farther than this (u, centre to centre)
    end_lo: float = 4.0          # ... never when it ends her nearer than this at the evade's end
    min_u: float = 3.2           # ... and never nearer than this on any frame (her box front 0.72 u off its front 2.25)
    stop_u: float = 3.6          # no key toward it nearer than this
    tap_f: int = 2               # the dash key held this many frames (a tap: the dash runs its 0.1 s on)
    dash_k_max: int = 18         # the latest evade frame (the mask's) of the dash (t1: 15 left the late landings from
    #                              a down slash's bounce at 6.5-7.8 u, no dash)
    air_dash: int = 1            # the air dash when the run alone ends Far
    air_if_u: float = 8.0        # ... beyond this (u; Close at <= 8.28)
    air_margin: float = 0.6      # ... its path keeps min_u + this, its end end_lo + this (the model is the facts')
    slash_cd: int = 19           # own presses this many frames apart (the Wanderer cooldown 0.3 s = 18)
    hit_lag: int = 2             # the slash meets it this many frames after the mask's frame
    reach_spare: float = 0.1     # the slash must overlap its body box by this much
    wall_back: float = 1.34      # its back from its centre (the slide stops when it meets the wall)
    dash: int = 1                # 0: no dash (run and slash only)
    slash: int = 1               # 0: no slash
    slash_k_min: int = 18        # no slash before this evade frame (the mask's; the hit at the slide's end)
    atk_cd_max: float = 0.19     # no dash while the STATE's attack cooldown is above this (s; 0.283 on the press's
    #                              STATE: the mask >= 7 frames after the press)
    dash_check_f: int = 3        # a dash not started (dash_cd up, a Dash clip) by its mask + this: try again


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


def air_travel(j: int) -> float:
    """Her travel (u) by frame j after an air dash's mask (a tap): AIR_DASH_F frames at DASH_V, the Air Sprint's
    AIR_SPRINT_F frames slowing from AIR_SPRINT_V0, then the air control with the key toward it (WALK_U)."""
    d = 0.0
    for jj in range(1, j + 1):
        if jj <= AIR_DASH_F:
            d += DASH_V / 60.0
        elif jj <= AIR_DASH_F + AIR_SPRINT_F:
            d += (AIR_SPRINT_V0 - AIR_SPRINT_DEC * (jj - AIR_DASH_F - 1)) / 60.0
        else:
            d += WALK_U
    return d


# SSBOT_FORUM_TWO_GUARD (SP11-0): the room (u) a dash / an air dash needs toward the focus before the other one's span
GUARD_DASH_U = DASH_V / 60.0 * DASH_F + WALK_U * 3 + 0.1
GUARD_AIR_U = air_travel(AIR_DASH_F + AIR_SPRINT_F + 3) + 0.1
GUARD_EXIT_U = 4.0           # ... inside a span: the chase on when its way out toward the focus is this short (the dash)


def air_path(d: float, n: int, slide: float) -> list[float]:
    """As dash_path for the air dash (frames 1 .. AIR_DASH_F + AIR_SPRINT_F + 3)."""
    return [d + min(slide, EV_V * min(j, n)) - air_travel(j) for j in range(1, AIR_DASH_F + AIR_SPRINT_F + 4)]


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
    air: bool = False           # the dash was the air dash
    dash_tries: int = 0         # dash masks sent (a retry when one did not start)
    presses: list = field(default_factory=list)   # (evade frame of the mask, her x)
    hits: list = field(default_factory=list)      # (evade frame, src)
    x_end: float | None = None  # her x in front of its centre on the last Evade Scuttle tick
    k_end: int | None = None
    next_st: str | None = None  # its first state after the slide
    sent: list = field(default_factory=list)      # (f, mask) of this run's masks
    ticks: int = 0
    guard_min: float | None = None   # SSBOT_FORUM_TWO_GUARD: the least room toward it seen (u)
    guard_stops: int = 0             # ... masks held back by it
    guard_kind: str | None = None    # ... the kind of span she was seen inside


class EvadeChase:
    def __init__(self, cfg: ChaseCfg | None = None, one: bool = True, two: bool = False):
        self.cfg = cfg or _num_env(ChaseCfg())
        self.one, self.two = one, two        # chase with one live Clapper / with two (SP9a TWO_CHASE)
        self.run: Chase | None = None
        self.done: list[Chase] = []
        self._seen: set = set()
        self.n_evade = 0
        self.why_not: dict = {}
        self._runes: dict = {}             # rune circle iid -> {"first": frame first seen, "lit": seen lit}
        self.guard_f: list = []            # SSBOT_FORUM_TWO_GUARD: frames of the chases not started for it
        self._over_away: int | None = None # this tick's 0 is the brake with her falling on its body: the key away from it

    def reset(self) -> None:
        self.run = None
        self.done = []
        self._seen = set()
        self.n_evade = 0
        self.why_not = {}
        self._runes = {}
        self.guard_f = []
        self._over_away = None

    def observe(self, f: int, s: dict) -> None:
        """Every tick (the policy calls it whichever script runs): the rune circles' first frame and lit state."""
        self._rune_threats(f, s)

    def _rune_threats(self, f: int, s: dict) -> list[tuple[float, float]]:
        """The x spans of the jump cast rune circles lit now or still to come (cast_stab's rule: present, not yet
        seen lit, first seen less than RUNE_LIVE_F frames ago)."""
        out = []
        for lo, hi, iid, lit in _cs.rune_spans(s):
            r = self._runes.setdefault(iid, {"first": f, "lit": False})
            if lit:
                r["lit"] = True
                out.append((lo, hi))
            elif not r["lit"] and f - r["first"] < _cs.RUNE_LIVE_F:
                out.append((lo, hi))
        return out

    def _rune_in_way(self, f: int, s: dict, e: dict, face: int) -> bool:
        """A threat span over her way to it: from her x to min_u in front of its centre."""
        hx = _sp.hero_x(s)
        near = float(e["pos"][0]) + face * self.cfg.min_u
        lo, hi = min(hx, near), max(hx, near)
        return any(a < hi and b > lo for a, b in self._rune_threats(f, s))

    def active(self) -> bool:
        return self.run is not None and self.run.phase == "run"

    def abort(self, why: str) -> None:
        if self.active():
            self._close("abort", why)

    def yield_to(self, s: dict) -> None:
        """Another script (the slam playbook, the jump antic scripts) sends the keys this tick: the slide over -> the
        run ends ("end", its next state); still sliding -> abort ("other")."""
        r = self.run
        if r is None or r.phase != "run":
            return
        st = _sp.control(self._by_iid(s, r.iid) if self.two else _sp.clapper(s))[0]
        if st != EVADE:
            r.next_st = st
            self._close("done", "end")
        else:
            self._close("abort", "other")

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
            out["air_dash"] += r.air
            out["dash_retry"] += max(0, r.dash_tries - 1)
            out["presses"] += len(r.presses)
            out["hits_in_run"] += len(r.hits)
            out[f"end_{r.phase}_{r.why}"] += 1
            if r.x_end is not None:
                out["end_close"] += r.x_end <= 8.28
        for k, v in self.why_not.items():
            out[f"no_{k}"] += v
        res = dict(out)
        res["chase_runs"] = [self._rec(r) for r in runs]
        if self.guard_f:
            res["guard_nostart_f"] = list(self.guard_f)
        return res

    @staticmethod
    def _rec(r: Chase) -> dict:
        out = {"f0": r.f0, "k0": r.k0, "x0": r.x0, "ground0": r.ground0, "dash_k": r.dash_k, "dash_x": r.dash_x,
               "dash_pred": r.dash_pred, "air": r.air, "dash_tries": r.dash_tries, "presses": r.presses, "hits": r.hits, "x_end": r.x_end, "k_end": r.k_end,
               "next": r.next_st, "end": r.phase, "why": r.why, "ticks": r.ticks}
        if r.guard_min is not None:
            out["guard_min"], out["guard_stops"] = r.guard_min, r.guard_stops   # SSBOT_FORUM_TWO_GUARD
            out["guard_kind"] = r.guard_kind
        return out

    # ---- the script ----

    @staticmethod
    def _by_iid(s: dict, iid) -> dict | None:
        return next((e for e in _sp.clappers(s) if e.get("iid") == iid), None)

    def _n_ok(self, s: dict) -> bool:
        n = len(_sp.clappers(s))
        return (n == 1 and self.one) or (n == 2 and self.two)

    def _pick(self, s: dict, focus) -> dict | None:
        """The Clapper of this tick: the run's; else with one live Clapper that one, with two (two=True) the focus
        when it is in Evade Scuttle (no focus: the nearer one in it)."""
        cs = _sp.clappers(s)
        if self.run is not None:
            return self._by_iid(s, self.run.iid) if self.two else _sp.clapper(s)
        if len(cs) == 2 and self.two:
            if focus is not None:
                e = self._by_iid(s, focus)
                return e if _sp.control(e)[0] == EVADE else None
            hx = _sp.hero_x(s)
            ev = [e for e in cs if _sp.control(e)[0] == EVADE]
            return min(ev, key=lambda e: abs(float(e["pos"][0]) - hx)) if ev else None
        return _sp.clapper(s)

    def step(self, f: int, s: dict, ground: bool, accepting: bool = True, latch=None, focus=None,
             block: str | None = None, guard: list | None = None) -> int | None:
        """The mask for frame f + 2 while the chase runs, else None. latch: m -> the key mask the oracle's hold filter
        latches at f + 2 when m is sent for it (None: m itself); focus: L2's target (two Clappers); block: why no chase
        may run now (SP10c TWO_JUMPHIT: the other one's landing), None: no block."""
        self._over_away = None
        if block is not None:
            if self.run is not None:
                self._close("abort", block)
            return None
        e = self._pick(s, focus) if self.two else _sp.clapper(s)
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
            if not self._n_ok(s):
                self._close("abort", "two")
                return None
            if self._rune_in_way(f, s, e, r.face):
                self._close("abort", "rune")
                return None
            room = self._guard_room(r, f, s, e, guard)
            if room is not None and room <= 0.0:
                self._close("abort", "guard")
                return None
            for ev in s.get("ev") or ():
                d = ev.get("d") or {}
                if ev.get("k") == "hit" and d.get("type_key") == CLAPPER:
                    dealt = d.get("dealt", d.get("amount"))
                    if dealt is None or float(dealt) > 0:
                        r.hits.append((k - SEND_AHEAD, str(d.get("src"))))
            m = self._step_run(r, f, k, s, e, ground, accepting, latch, room)
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
        if not self._n_ok(s):
            why = "two"
        elif x0 <= 0:
            why = "behind"
        elif hp <= 0:
            why = "dead"
        elif self._rune_in_way(f, s, e, face):
            why = "rune"
        room = None
        if why is None and guard is not None:
            c0 = Chase(iid=e.get("iid"), face=face, f0=f, k0=0, x0=x0, ground0=bool(ground), hp0=hp)
            room = self._guard_room(c0, f, s, e, guard)
            self._gk = c0.guard_kind
            if room is not None and room <= 0.0:
                why = "guard"
                self.guard_f.append([f, self._gk])  # SSBOT_FORUM_TWO_GUARD: the no-start frames and kinds (stats)
        if why is not None:
            self.why_not[why] = self.why_not.get(why, 0) + 1
            return None
        k = int(round(tin * 60.0)) + SEND_AHEAD
        self.run = Chase(iid=e.get("iid"), face=face, f0=f, k0=k, x0=round(x0, 3), ground0=bool(ground), hp0=hp)
        if room is not None:
            self.run.guard_min, self.run.guard_kind = c0.guard_min, c0.guard_kind
        m = self._step_run(self.run, f, k, s, e, ground, accepting, latch, room)
        self.run.sent.append((f, m))
        self.run.ticks += 1
        return m

    def _guard_room(self, r: Chase, f: int, s: dict, e: dict, guard: list | None) -> float | None:
        """SSBOT_FORUM_TWO_GUARD: her room (u) toward the focus from her x on the mask's frame before the other one's
        nearest danger span (0: she is inside one), None without guard spans."""
        if guard is None:
            return None
        from ssbot.combat import two_play as _tp
        xw, cx = self._x_mask(r, f, s, e)
        ex, room, kind = _tp.guard_exit(guard, xw, -r.face, own=r.iid)
        r.guard_kind = kind or r.guard_kind
        if kind is not None:
            # (fp1 fix, 3251a4a: 5 of 25 no-starts lost HP to the span she stood in) inside a span: the chase goes on
            # when its way toward the focus leaves it within GUARD_EXIT_U and short of its stop (an escape), else 0
            d = (xw - cx) * r.face
            room = ex + room if ex <= min(GUARD_EXIT_U, d - self.cfg.stop_u) else 0.0
        if r.guard_min is None or room < r.guard_min:
            r.guard_min = round(room, 2)
        return room

    def _x_mask(self, r: Chase, f: int, s: dict, e: dict) -> tuple[float, float]:
        """(her box centre's world x, its centre's world x) on the mask's frame f + 2: her velocity (or this run's own
        run keys in flight) and its velocity on."""
        h = s.get("hero") or {}
        vx = float((h.get("vel") or [0.0, 0.0])[0])
        xw = _sp.hero_x(s) + vx * SEND_AHEAD / 60.0
        ev = float((e.get("vel") or [0.0, 0.0])[0])
        cx = float(e["pos"][0]) + ev * SEND_AHEAD / 60.0
        return xw, cx

    def _step_run(self, r: Chase, f: int, k: int, s: dict, e: dict, ground: bool, accepting: bool, latch,
                  room: float | None = None) -> int:
        c = self.cfg
        room = 99.0 if room is None else room      # SSBOT_FORUM_TWO_GUARD: her room toward it (u)
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
        if (r.dash_k is not None and k - r.dash_k > c.dash_check_f and float(tm.get("dash_cd") or 0.0) <= 0.02
                and "Dash" not in clip and "Sprint" not in clip):
            r.dash_k = None                           # the dash did not start: may try again
            r.air = False
        # the slash's second frame (one rising edge)
        if r.presses and k - r.presses[-1][0] == 1:
            return M_A | toward
        # a slash when it reaches its body (moving away) two frames after the mask
        if c.slash and self._slash_ok(r, k, s, e, d, cx, tm, clip, prev, away):
            r.presses.append((k, round(d, 2)))
            return M_A | toward
        # a dash when the run alone ends too far and the dash keeps clear of it
        atk_lock = float(tm.get("atk_cd") or 0.0) > c.atk_cd_max
        if c.dash and r.dash_k is None and ground and accepting and k <= c.dash_k_max and not atk_lock:
            d_run = d + slide - WALK_U * n
            if d_run > c.dash_if_u and float(tm.get("dash_cd") or 0.0) <= 0.02 and not any(
                    x in clip for x in NO_ATK_CLIPS) and room >= GUARD_DASH_U:
                path = dash_path(d, n, slide)
                d_end = path[-1] if n >= len(path) else path[max(0, n - 1)]
                # the end: the evade's last frame (or the path's end when the evade ends later)
                if min(path) >= c.min_u and d_end >= c.end_lo and (latch is None or (
                        int(latch(toward | M_DASH)) & (M_L | M_R | M_DASH)) == toward | M_DASH):
                    r.dash_k, r.dash_x = k, round(d, 2)
                    r.dash_tries += 1
                    r.dash_pred = {"d_run": round(d_run, 2), "d_end": round(d_end, 2), "min": round(min(path), 2),
                                   "n": n}
                    return toward | M_DASH
        if c.dash and c.air_dash and r.dash_k is None and not ground and accepting and k <= c.dash_k_max and \
                not atk_lock:
            d_run = d + slide - WALK_U * n
            if d_run > c.air_if_u and float(tm.get("dash_cd") or 0.0) <= 0.02 and not any(
                    x in clip for x in NO_ATK_CLIPS) and room >= GUARD_AIR_U:
                path = air_path(d, n, slide)
                d_end = path[-1] if n >= len(path) else path[max(0, n - 1)]
                if min(path) >= c.min_u + c.air_margin and d_end >= c.end_lo + c.air_margin and (latch is None or (
                        int(latch(toward | M_DASH)) & (M_L | M_R | M_DASH)) == toward | M_DASH):
                    r.dash_k, r.dash_x, r.air = k, round(d, 2), True
                    r.dash_tries += 1
                    r.dash_pred = {"d_run": round(d_run, 2), "d_end": round(d_end, 2), "min": round(min(path), 2),
                                   "n": n, "air": True}
                    return toward | M_DASH
        if d - WALK_U < c.stop_u:
            if self._falling_on_it(d, h, ground, accepting):
                self._over_away = away
            return 0
        if room < WALK_U * (SEND_AHEAD + 1):
            r.guard_stops += 1
            return 0                                  # SSBOT_FORUM_TWO_GUARD: the next step meets the other's span
        return toward

    @staticmethod
    def _falling_on_it(d: float, h: dict, ground: bool, accepting: bool) -> bool:
        """She is in the air, her box over its body in front of its centre on the mask's frame (d: her x in front of its
        centre there), and comes down to its standing top before its slide has taken its front edge past her box. Past its
        centre (d <= 0) no: the run's away key comes from the side it started on and would point at the body."""
        box, vel = h.get("box"), h.get("vel") or ()
        if ground or not accepting or not box or len(box) != 4 or len(vel) < 2 or float(vel[1]) >= 0.0:
            return False
        half = (float(box[2]) - float(box[0])) / 2.0
        reach = BODY_FRONT + half
        if not 0.0 < d < reach:
            return False
        frames = SEND_AHEAD + (reach - d) / EV_V
        return float(box[1]) + float(vel[1]) * frames / 60.0 < BODY_TOP

    def yields_brake_to(self, mask: int, latch=None) -> bool:
        """This tick's 0 is the distance brake with her falling on its body, and mask moves her away from it with the key
        latching on the mask's frame: the policy sends mask and ends the run. Any other 0 or mask: False, the brake holds."""
        away = self._over_away
        return (away is not None and int(mask) & (M_L | M_R) == away
                and (latch is None or bool(int(latch(int(mask))) & away)))

    def _slash_ok(self, r: Chase, k: int, s: dict, e: dict, d: float, cx: float, tm: dict, clip: str, prev: int,
                  away: int) -> bool:
        c = self.cfg
        if k < c.slash_k_min or (r.presses and k - r.presses[-1][0] < c.slash_cd):
            return False
        if r.dash_k is not None and k - r.dash_k < (AIR_DASH_F + AIR_SPRINT_F if r.air else DASH_F) + 2:
            return False                              # an attack from the dash / sprint is a DashStab
        if any(x in clip for x in NO_ATK_CLIPS):
            return False
        cd = tm.get("atk_cd")
        if cd is not None and float(cd) * 60.0 - (SEND_AHEAD - 1) > 0.05:
            return False
        if prev & away:
            return False                              # the slash would go the other way
        if self.two:
            # SP9a S1: never a slash that meets the other Clapper's body during F's slide (it would decide at once)
            from ssbot.combat import two_play as _tp
            xb = cx + d * r.face
            for o in _sp.clappers(s):
                if o.get("iid") != r.iid and _tp.slash_meets(xb, -r.face, _tp.body_span(o), spare=-0.3):
                    return False
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
