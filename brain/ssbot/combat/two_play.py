"""Two Clappers, SP9a (task 1v1 SP9a, Forum_W_w13; the spec C:/ssbot/data/m2_play/switch/answer.txt section 5 S1-S6,
human_two/answer.txt R2-R7 and R9, buddy/answer.txt R1-R3; forum.md 76).

Every rule has its own switch, default off; with all off nothing here runs and every decision is the one before.
F = the focus (L2's target when it is a Clapper, else the Clapper nearer to her), B = the other one. Distances are
centre to centre (her box centre, its transform), + = in front of it (the side it faces); HeroBox 0.46 u wide.

  SSBOT_FORUM_TWO_CHASE    S1: chase F's Evade Scuttle (combat.evade_chase with two Clappers: the evading focus only,
                           never a slash that meets B's body during F's slide).
  SSBOT_FORUM_TWO_IDLEHIT  S2 (buddy R1 / R2): F's Idle (re-)entry - the first frame the STATE shows it, or its state
                           time starting again (a hit -> Dmg Attack -> Close Range -> CANCEL -> Idle in one frame while B
                           attacks) - starts IdleHit: on the ground, attack ready, the side slash from her x at the mask's
                           frame meeting its body (its collider) -> the press (the key toward it on the press frame, the
                           turn key one frame before when she faces away); out of reach -> the walk toward it when that
                           gets her into reach by WIN_F frames after the entry (else the planner). Only Idle reacts to a
                           hit, and a hit inside 0.25 s of the entry blocks its evade coin (Can Evade at 0.25 s) and makes
                           it decide at once (a close move within 8.3 u: slam / cast / evade). No start while B can reach
                           her (other_danger), over a rune circle, in the air (a hit from the air sends it into its attack
                           with her airborne: NOPOGO), without input.
  SSBOT_FORUM_TWO_CAST     S3: the small-rune low hop (combat.rune_lowhop, SP8d) on F's close casts with two Clappers
                           (the caster in Spell Antic nearest to her in front; no start / hand back while B can reach her).
                           The slam playbook on F's slams is TWO_PLAY (combat.slam_play, SP7).
  SSBOT_FORUM_TWO_SPACE    S5 (human_two R5-R7): (a) B entering Slam Antic with F-B < 16 u: L2's target is the slammer
                           for that slam (strike it; combat.tactics.gauntlet); (b) the stance never within 4 u of the one
                           not slamming while the other is in Slam Antic, never within 2.5 u (+ her half width) of a Clapper
                           in Idle / Walk / Evade / Cast / Recover; (c) a jump move (either Clapper): the stance not 4 -
                           8.3 u in front of its landing (behind it or >= 8.3 u in front, the nearer), the landing from its
                           take-off x and her x at its Jump Aim (gauntlet.jump_landing); (d) the big rune: the circle (its
                           landing + 6.48 u along its facing, r 7.19 + her half width) from the jump cast's Cast Slam
                           Antic until it burst - the stance outside. A stance rule (the planner's checks unchanged).
  SSBOT_FORUM_TWO_OPEN     S6 (switch answer section 4, human_two R3): the harness walks her left from the load
                           (combat.encounters' wave intro: the policy gets the keys only at the wave's activation, 2.5 s
                           after the load; the person moves 2.6-2.7 s before the Drop Antic) to x <= OPEN_X; from the wake
                           the Opening script walks to OPEN_X (c2's inner side, 3.97 u from its landing x 21.03) and slashes
                           c2 while its body is in reach (Drop In's last frames, Enter Land) until its first Idle; then the
                           rest (IdleHit hits it at the Idle entry, the focus rule keeps the nearer one).

    two = TwoPlay()                                   # per episode: two.reset()
    m = two.step(f, s, ground, accepting, focus, t)   # IdleHit / Opening: the mask for frame f + 2, or None
    prefs = two.space(prefs, s, t)                    # TWO_SPACE's stance
"""
from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field, replace

from ssbot.combat import cast_stab as _cs
from ssbot.combat import slam_play as _sp


def _on(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip() == "1"


CHASE = _on("SSBOT_FORUM_TWO_CHASE")
IDLEHIT = _on("SSBOT_FORUM_TWO_IDLEHIT")
CAST = _on("SSBOT_FORUM_TWO_CAST")
SPACE = _on("SSBOT_FORUM_TWO_SPACE")
OPEN = _on("SSBOT_FORUM_TWO_OPEN")
ANY = IDLEHIT or SPACE or OPEN          # the policy's TwoPlay object (CHASE / CAST live in their own scripts)

CLAPPER = _sp.CLAPPER
M_L, M_R, M_A = _sp.M_L, _sp.M_R, _sp.M_A
SEND_AHEAD = _sp.SEND_AHEAD
WALK_U = _sp.WALK_U
WALL_L, WALL_R = _sp.WALL_L, _sp.WALL_R
NO_ATK_CLIPS = ("Dash", "Sprint", "Skid")
HALF_W = 0.25
JUMP_ST = _sp.TWO_JUMP_ST
SLAM_ST = ("Slam Antic", "Slam 0", "Slam 1", "Slam Effects?", "Slam 2")
CAST_ST = ("Spell Antic", "Cast 1", "Cast 2")
BODY_ST = ("Idle", "Walk", "Evade Scuttle", "Spell Antic", "Cast 1", "Cast 2", "Slam Recover", "After Scuttle")
# the opening (fo_cl_w13w, 20 SP7 episodes: the two land at x 21.03 / 42.03; the person at Enter Land at x 24.0-26.3,
# 3.1-5.2 u in front of c2 on the inner side)
OPEN_C2_X = 21.03
OPEN_X = 25.0                # her x from the wake (c2 + 3.97 u: in the side slash's reach of its body front, 2.25 u)
OPEN_INTRO_X = 26.5          # the intro's walk stops here (the policy walks the rest)
OPEN_END_S = 4.0             # the opening script ends this long after the wake at the latest
WIN_F = 30                   # IdleHit: frames after the Idle entry it may still start (the coin fires at 15)


def clapper_by(s: dict, iid) -> dict | None:
    return next((e for e in _sp.clappers(s) if e.get("iid") == iid), None)


def face_of(e: dict) -> int:
    return 1 if e.get("flipX") else -1


def body_span(e: dict) -> tuple[float, float]:
    """Its body's x span: the STATE's collider, else the Idle box from its facing."""
    for col in e.get("colliders") or ():
        if col.get("name") == CLAPPER and col.get("enabled") and col.get("verts_world"):
            xs = col["verts_world"][0::2]
            return float(min(xs)), float(max(xs))
    cx, fc = float(e["pos"][0]), face_of(e)
    a, b = cx + fc * _sp.BODY_FRONT, cx - fc * _sp.BODY_BACK
    return min(a, b), max(a, b)


def body_y(e: dict) -> tuple[float, float]:
    """Its body's y span (the collider; else the standing box: transform - 4.45 .. - 0.53)."""
    for col in e.get("colliders") or ():
        if col.get("name") == CLAPPER and col.get("enabled") and col.get("verts_world"):
            ys = col["verts_world"][1::2]
            return float(min(ys)), float(max(ys))
    cy = float(e["pos"][1])
    return cy - 4.45, cy - 0.53


def slash_meets(xw: float, look: int, span: tuple[float, float], spare: float = 0.1) -> bool:
    """The side slash from her box centre at world x xw facing look (+1 right) meets the x span."""
    lo, hi = (xw + _sp.SLASH_X[0], xw + _sp.SLASH_X[1]) if look > 0 else (xw - _sp.SLASH_X[1], xw - _sp.SLASH_X[0])
    return lo < span[1] - spare and hi > span[0] + spare


def other_danger(s: dict, f_iid, x: float, runes: list | None = None) -> str | None:
    """Why the Clapper(s) other than f_iid can reach her x now (SP7's _two_danger with her x as the point): a jump move,
    its hammer / lunge within 12.5 u (Slam Antic .. Slam 2: the hammer reaches 12 u in front, from its centre), the small
    runes within 9 u, its recovering body within 4.5 u; a rune circle (lit or to come) over x."""
    for o in _sp.clappers(s):
        if o.get("iid") == f_iid:
            continue
        st = _sp.control(o)[0]
        cx = float(o["pos"][0])
        d = abs(cx - x)
        front = (x - cx) * face_of(o) > -1.5
        if st in JUMP_ST:
            return f"other {st}"
        if st in SLAM_ST and d < _sp.TWO_SLAM_U and front:
            return f"other {st}"
        if st in CAST_ST and d < _sp.TWO_CAST_U:
            return f"other {st}"
        if st == "Slam Recover" and d < _sp.TWO_BODY_U:
            return "other Slam Recover"
    for lo, hi in runes or ():
        if lo - HALF_W < x < hi + HALF_W:
            return "rune circle"
    return None


@dataclass
class IdleRun:
    iid: object
    f0: int                    # the STATE frame of the Idle (re-)entry
    re: bool                   # a re-entry (its state time started again)
    d0: float                  # her distance at the entry (u, centre to centre)
    hp0: int
    k_press: int | None = None  # frames from the entry to the press's mask
    k_hit: int | None = None    # frames from the entry to the landed hit (the STATE that shows it)
    walk: int = 0              # walk masks sent
    why: str = ""              # no start / end
    sent: list = field(default_factory=list)


class TwoPlay:
    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.prev: dict = {}             # iid -> (Control state, state time) on the last tick
        self.entry: dict = {}            # iid -> re-entry (bool) for the Clappers entering Idle this tick
        self.idle: IdleRun | None = None
        self.idle_done: list[IdleRun] = []
        self.no: Counter = Counter()
        self.open = {"on": False, "f_wake": None, "done": None, "presses": [], "walk": 0, "x_wake": None,
                     "hits": 0}
        self._press_f: int | None = None  # the last press's mask frame (the second frame follows)
        self._toward = 0
        self.jumps: dict = {}            # TWO_SPACE: iid -> {"x0", "face", "fam", "aim_hx", "land"}
        self.space_n: Counter = Counter()
        self._runes: dict = {}

    # ---- helpers ----

    def _rune_threats(self, f: int, s: dict) -> list[tuple[float, float]]:
        out = []
        for lo, hi, iid, lit in _cs.rune_spans(s):
            r = self._runes.setdefault(iid, {"first": f, "lit": False})
            if lit:
                r["lit"] = True
                out.append((lo, hi))
            elif not r["lit"] and f - r["first"] < _cs.RUNE_LIVE_F:
                out.append((lo, hi))
        return out

    def observe(self, f: int, s: dict, t: float) -> None:
        """Every tick: the Idle entries' bookkeeping (prev), the jump moves' take-off (TWO_SPACE), the rune circles."""
        self._rune_threats(f, s)
        hx = _sp.hero_x(s) if (s.get("hero") or {}).get("box") or (s.get("hero") or {}).get("pos") else None
        self.entry = {}
        for e in _sp.clappers(s):
            iid = e.get("iid")
            st, tin = _sp.control(e)
            # an Idle (re-)entry this tick: the first frame showing Idle, or its state time starting again (a hit ->
            # Dmg Attack -> Close Range -> CANCEL -> Idle in one frame while the buddy attacks)
            pst = self.prev.get(iid)
            if st == "Idle" and (pst is None or pst[0] != "Idle" or tin + 0.5 / 60.0 < pst[1]):
                self.entry[iid] = pst is not None and pst[0] == "Idle"
            self.prev[iid] = (st, tin)
            if SPACE and hx is not None:
                j = self.jumps.get(iid)
                if st in ("Jump Antic", "Cast Slam Antic") and (j is None or j.get("done")):
                    self.jumps[iid] = {"x0": float(e["pos"][0]), "face": face_of(e), "aim_hx": None,
                                       "fam": "jc" if st == "Cast Slam Antic" else "j", "t0": t, "done": False}
                elif j is not None and not j.get("done"):
                    if st in ("Jump", "Air") and j["aim_hx"] is None:
                        j["aim_hx"] = hx
                    if st not in JUMP_ST:
                        j["done"] = True
                        j["land_x"] = float(e["pos"][0])
                        j["t_land"] = t
        # the IdleHit run's bookkeeping on every tick (another script may hold the keys when its hit shows): the landed
        # hit on its Clapper (the STATE that shows it: its state turns over in the same frame), the run's end
        r = self.idle
        if r is not None:
            for ev in s.get("ev") or ():
                d = ev.get("d") or {}
                if ev.get("k") == "hit" and d.get("type_key") == CLAPPER and (d.get("ent") or d.get("iid")) == r.iid:
                    if r.k_hit is None and (d.get("dealt") is None or float(d.get("dealt")) > 0):
                        r.k_hit = f - r.f0
            e = clapper_by(s, r.iid)
            hp = int((s.get("hero") or {}).get("health") or 0)
            if e is None or len(_sp.clappers(s)) != 2:
                self._idle_close("gone" if e is None else "one")
            elif _sp.control(e)[0] != "Idle" or r.iid in self.entry or f - r.f0 > WIN_F or hp < r.hp0:
                self._idle_close("hit" if r.k_hit is not None else (
                    "hurt" if hp < r.hp0 else "re-entry" if r.iid in self.entry else
                    "left idle" if _sp.control(e)[0] != "Idle" else "window"))

    # ---- S2 IdleHit / S6 Opening ----

    def step(self, f: int, s: dict, ground: bool, accepting: bool, focus, t: float, wake_f: int | None = None,
             two_enc: bool = False) -> int | None:
        """The mask for frame f + 2 (IdleHit, the Opening), or None (the planner)."""
        m = None
        if OPEN and two_enc:
            m = self._open_step(f, s, ground, accepting, t, wake_f)
        idle_m = self._idle_step(f, s, ground, accepting, focus) if IDLEHIT else None
        return m if m is not None else idle_m

    def _press(self, f: int, toward: int) -> int:
        self._press_f, self._toward = f, toward
        return M_A | toward

    def _second(self, f: int) -> int | None:
        """The press's second frame (one rising edge, the key toward it)."""
        if self._press_f is not None and f - self._press_f == 1:
            return M_A | self._toward
        return None

    def _atk_ready(self, s: dict) -> bool:
        tm = (s.get("hero") or {}).get("tm") or {}
        cd = tm.get("atk_cd")
        clip = str(((s.get("hero") or {}).get("anim") or {}).get("clip") or "")
        if any(x in clip for x in NO_ATK_CLIPS):
            return False
        return cd is None or float(cd) * 60.0 - (SEND_AHEAD - 1) <= 0.05

    @staticmethod
    def _facing(s: dict, look: int) -> bool:
        fc = (s.get("hero") or {}).get("facing")
        return fc is not None and float(fc) * look > 0

    @staticmethod
    def _xw(s: dict, n: int = SEND_AHEAD) -> float:
        h = s.get("hero") or {}
        vx = float((h.get("vel") or [0.0, 0.0])[0])
        return _sp.hero_x(s) + vx * n / 60.0

    def _idle_step(self, f: int, s: dict, ground: bool, accepting: bool, focus) -> int | None:
        cs = _sp.clappers(s)
        sec = self._second(f)
        if sec is not None and self.idle is not None and self.idle.k_press is not None:
            self.idle.sent.append((f, sec))
            return sec
        r = self.idle
        h = s.get("hero") or {}
        hp = int(h.get("health") or 0)
        if len(cs) != 2:
            return None
        F = clapper_by(s, focus) if focus is not None else None
        if F is None:
            hx = _sp.hero_x(s)
            F = min(cs, key=lambda e: abs(float(e["pos"][0]) - hx))
        iid = F.get("iid")
        st, tin = _sp.control(F)
        entry = iid in self.entry
        if r is not None and (r.iid != iid or entry):
            self._idle_close("focus" if r.iid != iid else "re-entry")      # (observe closes the other ends)
            r = None
        if r is None and entry:
            hx = _sp.hero_x(s)
            r = self.idle = IdleRun(iid=iid, f0=f, re=bool(self.entry[iid]),
                                    d0=round(abs(hx - float(F["pos"][0])), 3), hp0=hp)
        if r is None or r.k_press is not None:
            return None
        k = f - r.f0
        hx = self._xw(s)
        cx = float(F["pos"][0])
        look = 1 if cx > hx else -1
        toward = M_R if look > 0 else M_L
        why = None
        if not accepting:
            why = "no input"
        elif not ground:
            why = "air"
        else:
            why = other_danger(s, iid, hx, self._rune_threats(f, s))
        if why is not None:
            r.why = r.why or why
            return None
        span = body_span(F)
        if slash_meets(hx, look, span):
            if not self._atk_ready(s):
                # in reach, the attack not ready: stand still when it is ready inside the window, else the planner
                cd = float(((h.get("tm") or {}).get("atk_cd")) or 0.0) * 60.0 - (SEND_AHEAD - 1)
                r.why = r.why or "cooldown"
                if k + cd <= WIN_F:
                    r.sent.append((f, 0))
                    return 0
                return None
            if not self._facing(s, look) and not (r.sent and r.sent[-1][1] & toward):
                r.sent.append((f, toward))
                return toward                     # the turn: she faces it on the next frame
            r.k_press = k
            m = self._press(f, toward)
            r.sent.append((f, m))
            return m
        gap = (span[0] - hx) if look > 0 else (hx - span[1])
        need = max(0.0, gap - (_sp.SLASH_X[1] - 0.15)) / WALK_U
        if k + need > WIN_F:
            r.why = r.why or "far"
            return None
        r.walk += 1
        r.sent.append((f, toward))
        return toward

    def _idle_close(self, why: str) -> None:
        r = self.idle
        if r is not None:
            r.why = r.why if (r.why and why in ("window", "left idle")) else why
            self.idle_done.append(r)
        self.idle = None

    def _open_step(self, f: int, s: dict, ground: bool, accepting: bool, t: float, wake_f: int | None) -> int | None:
        o = self.open
        if o["done"] is not None:
            return None
        if o["f_wake"] is None:
            o["f_wake"] = wake_f if wake_f is not None else f
            o["on"] = True
            o["x_wake"] = round(_sp.hero_x(s), 2)
        sec = self._second(f)
        if sec is not None and o["presses"] and o["presses"][-1][0] == f - 1:
            return sec
        h = s.get("hero") or {}
        cs = _sp.clappers(s)
        c2 = min(cs, key=lambda e: float(e["pos"][0])) if len(cs) == 2 else None
        st2 = _sp.control(c2)[0] if c2 is not None else None
        if (f - o["f_wake"]) / 60.0 > OPEN_END_S or st2 == "Idle" or (cs and len(cs) != 2):
            o["done"] = "c2 idle" if st2 == "Idle" else "time" if cs else "gone"
            return None
        for ev in s.get("ev") or ():
            d = ev.get("d") or {}
            if ev.get("k") == "hit" and d.get("type_key") == CLAPPER:
                o["hits"] += 1
        if not accepting:
            return None
        hx = self._xw(s)
        if c2 is not None and ground and st2 in ("Drop In", "Enter Land"):
            span = body_span(c2)
            y0, _ = body_y(c2)
            hy = float((h.get("pos") or [0.0, 0.0])[1])
            look = 1 if float(c2["pos"][0]) > hx else -1
            toward = M_R if look > 0 else M_L
            if slash_meets(hx, look, span) and y0 < hy + 0.9 and self._atk_ready(s):
                if not self._facing(s, look):
                    return toward
                o["presses"].append((f, round(hx - float(c2["pos"][0]), 2), st2))
                return self._press(f, toward)
        # the walk to OPEN_X (stop dead inside +-0.3 u)
        if abs(hx - OPEN_X) <= 0.3:
            return 0
        o["walk"] += 1
        return M_L if hx > OPEN_X else M_R

    # ---- S5 the stance ----

    def space(self, prefs, s: dict, t: float, focus):
        """TWO_SPACE (module docstring b-d): the stance moved out of the forbidden spans."""
        if not SPACE:
            return prefs
        cs = _sp.clappers(s)
        if len(cs) != 2 or not ((s.get("hero") or {}).get("box") or (s.get("hero") or {}).get("pos")):
            return prefs
        hx = _sp.hero_x(s)
        x = float(prefs.stance_x)
        spans = []                               # (lo, hi, why)
        slammer = next((e for e in cs if _sp.control(e)[0] == "Slam Antic"), None)
        sep = abs(float(cs[0]["pos"][0]) - float(cs[1]["pos"][0]))
        for e in cs:
            st = _sp.control(e)[0]
            cx = float(e["pos"][0])
            if slammer is not None and e is not slammer and sep < 16.0:
                # human_two R6: within 4 u of the one not slamming at a slam antic, HP lost 8 / 8 (the hammer covers
                # her path when the two are < 16 u apart, 0 / 19 at >= 16 u: switch answer 2f)
                spans.append((cx - 4.0 - HALF_W, cx + 4.0 + HALF_W, "slam: other 4u"))
            if st in BODY_ST:
                spans.append((cx - 2.5 - HALF_W, cx + 2.5 + HALF_W, "body 2.5u"))
            j = self.jumps.get(e.get("iid"))
            if j is not None and not j.get("done") and j["aim_hx"] is not None:
                # from its Jump Aim on (the landing follows her x until then)
                from ssbot.combat.tactics.gauntlet import jump_landing
                land = jump_landing(j["x0"], j["aim_hx"], j["face"])
                fc = j["face"]
                a, b = land + fc * 4.0, land + fc * 8.3
                spans.append((min(a, b) - HALF_W, max(a, b) + HALF_W, "jump landing 4-8.3u"))
                if j["fam"] == "jc":
                    c = land + fc * 6.48
                    spans.append((c - 7.19 - HALF_W, c + 7.19 + HALF_W, "big rune (to come)"))
        for lo, hi in self._rune_threats(int(s.get("f") or 0), s):
            spans.append((lo - HALF_W, hi + HALF_W, "rune circle"))
        hit = [sp_ for sp_ in spans if sp_[0] < x < sp_[1]]
        if not hit:
            return prefs
        # the nearest x to the stance outside every span, inside the arena (the walls' pad 0.5 u)
        cands = sorted({sp_[0] for sp_ in spans} | {sp_[1] for sp_ in spans})
        best = None
        for c in cands:
            for xx in (c - 0.05, c + 0.05):
                if not WALL_L + 0.5 <= xx <= WALL_R - 0.5:
                    continue
                if any(a < xx < b for a, b, _ in spans):
                    continue
                if best is None or abs(xx - x) < abs(best - x):
                    best = xx
        if best is None:
            self.space_n["no_free_x"] += 1
            return prefs
        for _, _, why in hit:
            self.space_n[why] += 1
        return replace(prefs, stance_x=float(best))

    # ---- stats ----

    def stats(self) -> dict:
        out = Counter(self.no)
        runs = self.idle_done + ([self.idle] if self.idle is not None else [])
        for r in runs:
            out["idle_runs"] += 1
            out["idle_re"] += r.re
            out["idle_press"] += r.k_press is not None
            out["idle_hit"] += r.k_hit is not None
            out["idle_walk_runs"] += r.walk > 0
            out[f"idle_end_{r.why}"] += 1
        res = dict(out)
        res["idle_runs_rec"] = [[r.f0, r.re, r.d0, r.k_press, r.k_hit, r.walk, r.why] for r in runs]
        res["space"] = dict(self.space_n)
        if OPEN:
            res["open"] = {k: v for k, v in self.open.items()}
        return res


def intro_keys(s: dict) -> int:
    """SSBOT_FORUM_TWO_OPEN: the harness's key mask in the wave-start intro (the load -> the wave's activation): left
    while her x is right of OPEN_INTRO_X, else none."""
    h = s.get("hero") or {}
    if not (h.get("box") or h.get("pos")) or not h.get("hero_accepting_input", True):
        return 0
    return M_L if _sp.hero_x(s) > OPEN_INTRO_X else 0

