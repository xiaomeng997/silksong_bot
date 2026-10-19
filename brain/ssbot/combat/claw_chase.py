"""SP10c: SSBOT_FORUM_CLAW_CHASE - the late Clawline on a far jump (the person's Clawline ideas of 2026-10-17; the spec
C:/ssbot/data/m2_play/clawline/answer.txt sections 2-4; forum.md 81). Default off.

J = the Clapper whose far jump slam / jump cast comes at her (Jump Antic / Cast Slam Antic, facing her, her centre
8.4-12.2 u from its centre); I = the other one (two Clappers). Frames k from J's antic entry (the STATE frame minus its
state time), JA = its Jump Aim (the first flight frame: +29 / 30 for a jump, +54-56 for a jump cast).

  hop    the jump key held hop_hold (10) frames from k_hop (a jump: antic + 2; a jump cast: JA - 25): her box bottom
         2.97-3.35 u above the floor at the apex (+14), over the small-rune bombs (lit bomb top 2.82 u; her air HeroBox
         bottom 0.53 u above her box bottom)
  press  the Clawline key (S) with the key toward J at JA + press_rel (-10; the model: -16 .. -13 lets the dash's damager
         meet the rising body), one frame of the turn key before; the needle's ray check (once, ~9 frames after the
         press: J still in its antic, her box bottom + 0.50 .. + 1.98 u, reach 10.5 u) hooks it, the dash (+18-19, 70 u/s,
         at most 0.1 s) stops on the first Dash Damager contact ~2 u short of its body: 2 x 5 HP, silk -1 then +1; the
         hooked Clapper's body contact is off until 0.2 s after control returns (Harpoon Dash End -> Wait 0.2 -> Idle ->
         ResetRecordedDamageHero); no stagger (a jump / cast is not interrupted)
  lock   no key until control returns (+25-30 after the press; hero_accepting_input and no Harpoon clip)
  after  variant A: at control the air dash (dash_hold frames) toward its take-off side (-J's facing) - through its
         body while its contact is still off - ending 5.6-7.2 u behind its landing (+84-85); then no key until she lands
         (the planner walks in and slashes its back in Slam Recover). Without it the bounce (+4.08 u, peak 0.37 s after
         control) meets its flying body (the model: 1,622 / 1,754).
         variant B (the person): no dash; drift toward its back (-J's facing) and down-slash its head when its body is
         below her within reach (twice if a bounce gives the time), until she lands or it is in Slam Recover.
Scope: SSBOT_FORUM_CLAW_SCOPE "bomb" (the spec's rule, two Clappers: a lit small-rune bomb on her ground path to the
slash spot) or "any" (the test arm: every far jump that passes the geometric gates, one or two Clappers).
SSBOT_FORUM_CLAW_VAR "A" / "B"; SSBOT_FORUM_CLAW_SET "press_rel=-10,hop_hold=10" trial overrides (a value list
"press_rel=-13|-10|-8" cycles per run: the fixed-point trials).

    cc = ClawChase()                                     # per episode: cc.reset()
    m = cc.step(f, s, ground, accepting, t)              # the mask for frame f + 2 while the run holds the keys, or None
"""
from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field

from ssbot.combat import slam_play as _sp
from ssbot.combat import two_play as _tp


def _on(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip() == "1"


ENABLED = _on("SSBOT_FORUM_CLAW_CHASE")
# SSBOT_FORUM_TWO_CLAWAIR (task 1v1 SP14, default off; the person 2026-10-18 19:10 / 20:30, the lead's ADDENDUM 3: "hit by
# the big rune many times, mostly while Hornet is in the AIR and the Clapper jumps over to her"): the airborne start of
# variant A. She is in the air (no hop) at a Clapper's jump antic or early flight, in front of it, inside its landing's
# reach (the hammer 7.76 u / the circle 13.67 u in front, its body 1.6 u behind; the landing from jump_behind.landing),
# silk >= 1, the other one neither jumping nor in the way: the press frame P is the earliest one whose ray check (P + 10)
# meets its body - the flight's box from rune_pogo.FLIGHT_Y0 (bottom above the floor every 6 frames from its aim, x
# linear from the take-off to the landing, 3.8 u high, 1.34 behind / 2.25 in front) - inside her band (her box bottom
# at the throw yP - 0.261 + 0.0788 vyP: CLAWSTRIKE's fit, vy -6 .. +9 u/s; her fall from now with g 0.0169 u/f^2;
# the band + 0.50 .. + 1.98 u, overlap >= ca_ovl), its near edge 0.5 .. 10.5 u ahead after the antic's 1.25 u drift,
# and control (P + 32) at its flight frame <= ca_ctrl_k (its body still high above her: the air dash at control goes
# under it to its take-off side, the landing behind its landing - the hammer / the circle in front). The rest is
# variant A's run (lock, the air dash, no key to her landing). Far jumps only (her centre >= ca_dmin 7 u from its
# centre: JUMP_BEHIND's aim stance at 5.5 u makes it jump in place). SSBOT_FORUM_TWO_CLAWAIR_SET "scope=any" (the fixed
# points: every airborne case in front within 12 u), "ca_ovl=0.4,ca_ctrl_k=40".
CLAWAIR = _on("SSBOT_FORUM_TWO_CLAWAIR")
CA = {"scope": "reach", "ca_ovl": 0.4, "ca_ctrl_k": 40.0, "ca_kmax": 30.0, "ca_dmin": 7.0}
for _kv in os.environ.get("SSBOT_FORUM_TWO_CLAWAIR_SET", "").replace(";", ",").split(","):
    if "=" in _kv:
        _k, _v = (_x.strip() for _x in _kv.split("=", 1))
        if _k not in CA:
            raise KeyError(f"SSBOT_FORUM_TWO_CLAWAIR_SET: unknown key {_k!r}")
        CA[_k] = _v if _k == "scope" else float(_v)
CA_G = 0.0169               # her gravity in the air (u / frame^2; the bounce's 4.08 u peak at 22 frames)
CA_DY0, CA_DYV = -0.261, 0.0788   # claw_strike's throw fit (her box bottom at the throw from yP, vyP in u/s)
CA_CTRL = 32                # control after the press (p50; 26-34)
FLIGHT_Y0 = (0.8, 4.1, 6.6, 8.2, 9.0, 8.9, 8.0, 6.3, 3.7, 0.3, 0.0)   # rune_pogo.FLIGHT_Y0 (every 6 frames from the aim)
FLIGHT_F = 54               # the flight's frames (aim -> landing)
CA_BOMB_U = 3.0             # fp1: no start with a small-rune bomb this near her way (u)
VARIANT = os.environ.get("SSBOT_FORUM_CLAW_VAR", "A").strip().upper() or "A"
SCOPE = os.environ.get("SSBOT_FORUM_CLAW_SCOPE", "bomb").strip() or "bomb"
M_L, M_R, M_J, M_A, M_D, M_DASH = _sp.M_L, _sp.M_R, _sp.M_J, _sp.M_A, _sp.M_D, _sp.M_DASH
M_CLAW = 1 << 4             # the clawline button (ssbot.ipc.framing.BUTTONS order; key S)
SEND_AHEAD = _sp.SEND_AHEAD
JUMP_ANTIC = ("Jump Antic", "Cast Slam Antic", "Cast Slam Antic 2")
FLIGHT = ("Jump Aim", "Cast Jump", "Jump", "Air")
LAND = ("Slam 2", "Slam Effects?", "Slam Recover")
HARPOON_CLIPS = ("Harpoon",)
BOMB_R = 2.42               # a lit small-rune bomb's reach along x (r 2.166 + her half width)


@dataclass
class ClawCfg:
    d_min: float = 8.4        # her centre from J's centre at the antic (u)
    d_max: float = 12.2
    ja_j: int = 30            # Jump Aim (the first flight frame) after the antic entry: a jump / a jump cast
    ja_c: int = 55
    hop_j: int = 2            # the hop's first mask frame: a jump (antic + 2) / a jump cast (JA - 25)
    hop_c_rel: int = -25
    hop_hold: str = "10"      # frames of the jump key (a "|" list cycles per run)
    press_rel: str = "-10"    # the Clawline press relative to JA (a "|" list cycles per run)
    press_f: int = 2          # frames the Clawline key is held
    after: str = "dash"       # variant A: "dash" (the air dash at control) / "none" (a "|" list cycles per run)
    dash_hold: int = 2        # frames of the air dash key
    lock_max: int = 45        # the lock ends this many frames after the press at the latest (control or not)
    end_f: int = 75           # the run ends this many frames after control at the latest
    ds_reach: float = 1.4     # variant B: |its x - her x| for the down slash (u) ...
    ds_top: float = 2.6       # ... with its body top this far below her box bottom at most
    ds_max: int = 2
    ray_gate: int = 1         # (A/B fix) no start with the other Clapper in the way (between her and J or just past it)


def _cfg() -> ClawCfg:
    c = ClawCfg()
    for kv in os.environ.get("SSBOT_FORUM_CLAW_SET", "").replace(";", ",").split(","):
        if "=" not in kv:
            continue
        k, v = (x.strip() for x in kv.split("=", 1))
        if not hasattr(c, k):
            raise KeyError(f"SSBOT_FORUM_CLAW_SET: unknown key {k!r}")
        cur = getattr(c, k)
        setattr(c, k, v if isinstance(cur, str) else type(cur)(float(v)))
    return c


def _pick(spec: str, n: int) -> str:
    vals = [x for x in str(spec).split("|") if x != ""]
    return vals[n % len(vals)] if vals else spec


@dataclass
class ClawRun:
    J: object
    I: object | None
    kind: str                  # "jump" / "cast"
    f_a: int                   # J's antic entry (STATE frame - its state time)
    x0: float                  # J's x and facing at the start
    face: int
    d0: float                  # her distance then (u, centre to centre)
    y0: float                  # her box bottom then (above the floor)
    hp0: int
    silk0: int
    why: str                   # the gate that let it start (scope)
    hop_hold: int = 10
    press_rel: int = -10
    after: str = "dash"
    k_hop: int = 0
    k_press: int = 0
    phase: str = "wait"        # wait -> hop -> air -> press -> lock -> after -> done
    k_ctrl: int | None = None  # control back (frames - f_a)
    hook: list = field(default_factory=list)       # frames (- f_a) of the Clawline's hits on J
    hits: list = field(default_factory=list)       # (frame - f_a, target J/I, src) of her other landed hits
    hp: list = field(default_factory=list)         # (frame - f_a, source)
    y_press: float | None = None   # her box bottom at the press / the ray check (press + 9)
    y_ray: float | None = None
    gap_ctrl: float | None = None  # her x to J's centre along its facing at control (+ = in front)
    k_land_j: int | None = None    # J's landing (Slam 2), frames - f_a
    x_land_j: float | None = None
    u_land: float | None = None    # her x along J's facing from its landing x at J's landing (- = behind it)
    k_land_her: int | None = None  # her landing after control
    ds: list = field(default_factory=list)         # variant B: the down slashes' mask frames (- f_a)
    sent: list = field(default_factory=list)
    end: str = ""
    f_end: int | None = None


class ClawChase:
    def __init__(self, cfg: ClawCfg | None = None):
        self.cfg = cfg or (_cfg() if ENABLED else ClawCfg())
        self.reset()

    def reset(self) -> None:
        self.run: ClawRun | None = None
        self._ca_tried: dict = {}                       # SP14 CLAWAIR: J iid -> (antic entry, aim frame, run started)
        self._ca_x0: dict = {}                          # SP14 CLAWAIR: J iid -> (take-off x, landing x)
        self.done: list[ClawRun] = []
        self.n: Counter = Counter()
        self._prev: dict = {}
        self._runs = 0

    # ---- the gates ----

    def _bomb_on_path(self, s: dict, hx: float, e: dict) -> bool:
        """The spec's rule (two Clappers): a small-rune bomb (lit, or appeared and still to light: rune_bombs.bomb_ents)
        within BOMB_R of her ground path from her x to the slash spot behind J's landing (its landing - 4.15 u along its
        facing), or the other Clapper in its cast (Spell Antic .. Cast 2: its rings light outward over the next ~1.7 s)
        with its centre within its ring reach (25 u) of that path."""
        from ssbot.combat import rune_bombs as _rb
        face = _tp.face_of(e)
        land = _tp.TwoPlay._landing(float(e["pos"][0]), hx, face)
        spot = land - face * 4.15
        lo, hi = min(hx, spot), max(hx, spot)
        for _, bx, _, _ in _rb.bomb_ents(s.get("ents")):
            if lo - BOMB_R < bx < hi + BOMB_R:
                return True
        for o in _sp.clappers(s):
            if o is e:
                continue
            if _sp.control(o)[0] in _tp.CAST_ST:
                ox = float(o["pos"][0])
                if lo - 25.0 < ox < hi + 25.0:
                    return True
        return False

    @staticmethod
    def _in_way(hx: float, cx: float, o: dict) -> bool:
        """The spec's gate (answer.txt section 3): the other Clapper's body between her and J, or within 3 u past J (the
        dash's damager stops her on the first enemy it meets; the needle hooks the nearer body in its band). (A/B
        5e48c0c, w13 scope any: 3 of 5 runs with the other one in the way, the dash stopped 4.9-8.6 u short of J, 1 hit,
        then J's body.)"""
        a, b = min(hx, cx), max(hx, cx)
        lo, hi = _tp.body_span(o)
        pad = 3.0
        return lo - _tp.HALF_W < b + (pad if cx > hx else 0.0) and hi + _tp.HALF_W > a - (pad if cx < hx else 0.0)

    def _start(self, f: int, s: dict, e: dict, ground: bool, accepting: bool) -> None:
        c = self.cfg
        st, tin = _sp.control(e)
        cs = _sp.clappers(s)
        h = s.get("hero") or {}
        hx = _sp.hero_x(s)
        cx = float(e["pos"][0])
        face = _tp.face_of(e)
        d = abs(hx - cx)
        self.n["antics"] += 1
        why = None
        if (hx - cx) * face <= 0:
            why = "behind"
        elif not c.d_min <= d <= c.d_max:
            why = "dist"
        elif not ground or not accepting:
            why = "air" if not ground else "no input"
        elif int(h.get("silk") or 0) < 1 or not ((h.get("can") or {}).get("harpoon", True)):
            why = "silk"
        elif len(cs) == 2 and any(_sp.control(o)[0] in _tp.JUMP_ST for o in cs if o is not e):
            why = "other jumping"
        elif len(cs) == 2 and c.ray_gate and any(self._in_way(hx, cx, o) for o in cs if o is not e):
            why = "other in the way"
        elif SCOPE != "any":
            if len(cs) != 2:
                why = "one"
            elif not self._bomb_on_path(s, hx, e):
                why = "no bomb"
        if why is not None:
            self.n[f"no_{why}"] += 1
            return
        o = next((x for x in cs if x is not e), None)
        kind = "jump" if st == "Jump Antic" else "cast"
        f_a = f - int(round(tin * 60.0))
        if st == "Cast Slam Antic 2" or f + SEND_AHEAD - f_a > (c.hop_j + 3 if kind == "jump"
                                                                 else c.ja_c + c.hop_c_rel - 1):
            self.n["no_late"] += 1                       # (first seen past its hop frame)
            return
        n = self._runs
        self._runs += 1
        ja = c.ja_j if kind == "jump" else c.ja_c
        hb = (h.get("box") or [0, _sp.FLOOR_Y - 1.56, 0, 0])
        r = ClawRun(J=e.get("iid"), I=None if o is None else o.get("iid"), kind=kind, f_a=f_a, x0=round(cx, 3),
                    face=face, d0=round(d, 2), y0=round(float(hb[1]) - (_sp.FLOOR_Y - 1.56), 2),
                    hp0=int(h.get("health") or 0), silk0=int(h.get("silk") or 0), why=SCOPE,
                    hop_hold=int(float(_pick(c.hop_hold, n))), press_rel=int(float(_pick(c.press_rel, n))),
                    after=_pick(c.after, n) if VARIANT == "A" else "B")
        r.k_hop = max(c.hop_j if kind == "jump" else ja + c.hop_c_rel, f + SEND_AHEAD - f_a)
        r.k_press = ja + r.press_rel
        self.run = r
        self.n["runs"] += 1
        self.n[f"runs_{kind}"] += 1

    def _start_air(self, f: int, s: dict, e: dict) -> None:
        """SSBOT_FORUM_TWO_CLAWAIR (module note at CLAWAIR): variant A from the air - the press frame from her fall and
        its flight's body; re-tried every tick of the move until a run starts or its flight frame passes ca_kmax."""
        c = self.cfg
        st, tin = _sp.control(e)
        iid = e.get("iid")
        cs = _sp.clappers(s)
        h = s.get("hero") or {}
        hx = _sp.hero_x(s)
        cx = float(e["pos"][0])
        face = _tp.face_of(e)
        rec = self._ca_tried.get(iid)
        if rec is None or rec[2]:
            return                                       # its antic not seen, or a run on this move already
        f_a, aim = rec[0], rec[1]
        jc = rec[3]
        k_now = f + SEND_AHEAD - aim                     # its flight frame of the mask frame
        if k_now > CA["ca_kmax"] or (hx - cx) * face <= 0:
            return
        if abs(hx - cx) < CA["ca_dmin"]:
            return                                       # a near jump (the person's: far jumps; 1v1's aim stance)
        if int(h.get("silk") or 0) < 1 or not ((h.get("can") or {}).get("harpoon", True)):
            self.n["ca_no_silk"] += 1
            return
        if len(cs) == 2 and any(_sp.control(o)[0] in _tp.JUMP_ST for o in cs if o is not e):
            return
        if len(cs) == 2 and c.ray_gate and any(self._in_way(hx, cx, o) for o in cs if o is not e):
            self.n["ca_no_way"] += 1
            return
        # fp1 (cbd3332, w13 jta, 32 episodes: 16 runs, 12 without HP lost; all 4 losses small-rune bombs - the run hangs
        # her in the air without i-frames over the other one's rows): none while the other one casts or a bomb (lit or
        # to light) lies within CA_BOMB_U of her x or between her and its take-off x (the dash back's way)
        if any(_sp.control(o)[0] in _tp.CAST_ST for o in cs if o is not e):
            self.n["ca_no_cast"] += 1
            return
        from ssbot.combat import rune_bombs as _rb
        lo_b, hi_b = min(hx, cx) - CA_BOMB_U, max(hx, cx) + CA_BOMB_U
        if any(lo_b < bx < hi_b for _, bx, _, _ in _rb.bomb_ents(s.get("ents"))):
            self.n["ca_no_bomb"] += 1
            return
        from ssbot.combat import jump_behind as _jb
        if self._ca_x0.get(iid) is not None:
            x0, land = self._ca_x0[iid]
        else:
            x0, land = cx, _jb.landing(cx, hx, face)
        rel = (hx - land) * face
        if CA["scope"] != "any" and not (-1.6 <= rel <= (13.67 if jc else 7.76) + 0.25):
            return
        if CA["scope"] == "any" and abs(hx - cx) > 12.0:
            return
        hb = h.get("box") or [0, _sp.FLOOR_Y - 1.56, 0, 0]
        y = float(hb[1]) - (_sp.FLOOR_Y - 1.56)          # her box bottom above the floor
        vy = float((h.get("vel") or [0.0, 0.0])[1]) / 60.0   # u / frame
        P = None
        for d in range(SEND_AHEAD + 1, 40):              # (one frame for the turn key before the press)
            kP = f + d - aim
            if kP + CA_CTRL > CA["ca_ctrl_k"]:
                break
            yP = y + vy * d - 0.5 * CA_G * d * d
            vyP = (vy - CA_G * d) * 60.0
            if yP < 0.3 or not -6.0 <= vyP <= 9.0:
                continue
            yb = yP + CA_DY0 + CA_DYV * vyP
            kr = kP + 10
            if kr < 0:
                jb, jx = 0.0, x0
            else:
                i = min(kr / 6.0, len(FLIGHT_Y0) - 1.0)
                i0 = int(i)
                i1 = min(i0 + 1, len(FLIGHT_Y0) - 1)
                jb = FLIGHT_Y0[i0] + (FLIGHT_Y0[i1] - FLIGHT_Y0[i0]) * (i - i0)
                jx = x0 + (land - x0) * min(kr / FLIGHT_F, 1.0)
            ovl = min(yb + 1.98, jb + 3.8) - max(yb + 0.5, jb)
            gap = (hx - face * 1.25 - (jx + face * 2.25)) * face    # her x after the antic's drift to its near edge
            if ovl >= CA["ca_ovl"] and 0.5 <= gap <= 10.5:
                P = f + d
                break
        if P is None:
            self.n["ca_no_band"] += 1
            return
        o = next((x for x in cs if x is not e), None)
        self._runs += 1
        r = ClawRun(J=iid, I=None if o is None else o.get("iid"), kind="cast" if jc else "jump", f_a=f_a,
                    x0=round(x0, 3), face=face, d0=round(abs(hx - cx), 2), y0=round(y, 2),
                    hp0=int(h.get("health") or 0), silk0=int(h.get("silk") or 0), why="air", hop_hold=0,
                    press_rel=int(P - aim), after="dash")
        r.k_hop = f + SEND_AHEAD - f_a
        r.k_press = P - f_a
        r.phase = "air"
        self.run = r
        self._ca_tried[iid] = (f_a, aim, True, jc)
        self.n["runs"] += 1
        self.n["ca_runs"] += 1
        self.n[f"ca_runs_{r.kind}"] += 1

    def ca_observe(self, f: int, s: dict) -> None:
        """SP14 CLAWAIR: every tick - each Clapper's antic entry and aim frame (from its state times) and its take-off x
        and landing (the first flight tick's: the hero's x then stands for hers at its Jump Aim; jump_behind.landing)."""
        from ssbot.combat import jump_behind as _jb
        c = self.cfg
        for e in _sp.clappers(s):
            iid = e.get("iid")
            st, tin = _sp.control(e)
            old = self._ca_tried.get(iid)
            if st in ("Jump Antic", "Cast Slam Antic"):
                f_a = f - int(round(tin * 60.0))
                if old is None or old[0] != f_a:
                    jc = st == "Cast Slam Antic"
                    self._ca_tried[iid] = (f_a, f_a + (c.ja_c if jc else c.ja_j), False, jc)
                    self._ca_x0.pop(iid, None)
            elif st in ("Jump Aim", "Cast Jump", "Jump") and self._ca_x0.get(iid) is None and old is not None:
                cx = float(e["pos"][0])
                self._ca_x0[iid] = (cx, _jb.landing(cx, _sp.hero_x(s), _tp.face_of(e)))
                self._ca_tried[iid] = (old[0], f - int(round(tin * 60.0)), old[2], old[3])
            elif st not in ("Air", "Cast Slam Antic 2", "Jump Aim", "Cast Jump", "Jump"):
                self._ca_x0.pop(iid, None)

    # ---- the run ----

    def _close(self, f: int, why: str) -> None:
        r = self.run
        if r is not None:
            r.end, r.f_end = why, f - r.f_a
            self.done.append(r)
            self.n[f"end_{why}"] += 1
        self.run = None

    def _observe(self, f: int, s: dict) -> None:
        r = self.run
        k = f - r.f_a
        for ev in s.get("ev") or ():
            d = ev.get("d") or {}
            if ev.get("k") == "hit" and d.get("type_key") == _sp.CLAPPER:
                who = d.get("ent") or d.get("iid")
                src = str(d.get("src") or "")
                if "Harpoon" in src and who == r.J:
                    r.hook.append(k)
                elif d.get("dealt") is None or float(d.get("dealt")) > 0:
                    r.hits.append((k, "J" if who == r.J else "I", src[:16]))
            elif ev.get("k") == "hp" and (d.get("delta") or 0) < 0:
                r.hp.append((k, str(d.get("source"))[:40]))
        e = _tp.clapper_by(s, r.J)
        if e is not None:
            st = _sp.control(e)[0]
            if st in LAND and r.k_land_j is None:
                r.k_land_j = k
                r.x_land_j = round(float(e["pos"][0]), 3)
                r.u_land = round((_sp.hero_x(s) - r.x_land_j) * r.face, 2)

    def step(self, f: int, s: dict, ground: bool, accepting: bool, t: float | None = None, **kw) -> int | None:
        """kw req (SP12b, SSBOT_FORUM_TWO_RT2): when passed, a run starts only on the jump cast TwoPlay handed over
        ((the caster's iid, its antic entry frame) or None: no start)."""
        if not (ENABLED or CLAWAIR):
            return None
        cs = _sp.clappers(s)
        now = {e.get("iid"): _sp.control(e)[0] for e in cs}
        prev, self._prev = self._prev, now
        if CLAWAIR:
            self.ca_observe(f, s)
        h = s.get("hero") or {}
        if not (h.get("box") or h.get("pos")):
            return None
        if self.run is None:
            ext = "req" in kw
            req = kw.get("req")
            for e in cs:
                st = now.get(e.get("iid"))
                if ext and (req is None or e.get("iid") != req[0]):
                    continue
                if ENABLED and st in ("Jump Antic", "Cast Slam Antic") and prev.get(e.get("iid")) not in JUMP_ANTIC:
                    self._start(f, s, e, ground, accepting)
                    if self.run is not None:
                        break
            if self.run is None and CLAWAIR and not ext and not ground and accepting:
                for e in cs:
                    if now.get(e.get("iid")) in JUMP_ANTIC + ("Jump Aim", "Cast Jump", "Jump", "Air"):
                        self._start_air(f, s, e)
                        if self.run is not None:
                            break
            if self.run is None:
                return None
        r = self.run
        self._observe(f, s)
        c = self.cfg
        e = _tp.clapper_by(s, r.J)
        k = f + SEND_AHEAD - r.f_a                     # the mask's frame
        hp = int(h.get("health") or 0)
        clip = str((h.get("anim") or {}).get("clip") or "")
        hx = _sp.hero_x(s)
        y = float((h.get("box") or [0, 0])[1]) - (_sp.FLOOR_Y - 1.56)
        if e is None:
            self._close(f, "gone")
            return None
        if hp < r.hp0 and r.phase not in ("after",):
            self._close(f, "hurt")
            return None
        toward = M_R if float(e["pos"][0]) > hx else M_L
        back = M_R if -r.face > 0 else M_L             # toward its take-off side / its back
        if r.phase == "wait":
            if k < r.k_hop:
                return self._send(r, f, 0)
            r.phase = "hop"
        if r.phase == "hop":
            if k < r.k_hop + r.hop_hold:
                return self._send(r, f, M_J)
            r.phase = "air"
        if r.phase == "air":
            if ground and k > r.k_hop + 6:
                self._close(f, "landed early")
                return None
            if k < r.k_press - 1:
                return self._send(r, f, 0)
            if k == r.k_press - 1:
                return self._send(r, f, toward)        # the turn: she faces it on the press frame
            r.phase = "press"
            r.y_press = round(y, 2)
        if r.phase == "press":
            if k < r.k_press + c.press_f:
                return self._send(r, f, M_CLAW | toward)
            r.phase = "lock"
        if r.phase == "lock":
            if r.y_ray is None and k >= r.k_press + 9:
                r.y_ray = round(y, 2)
            harp = clip.startswith(HARPOON_CLIPS)
            if (accepting and not harp and k > r.k_press + 12) or k > r.k_press + c.lock_max:
                r.phase = "after"
                r.k_ctrl = f - r.f_a
                r.gap_ctrl = round((hx - float(e["pos"][0])) * r.face, 2)
                self.n["hooked" if r.hook else "missed"] += 1
            else:
                return self._send(r, f, 0)
        if r.phase == "after":
            j = f - r.f_a - r.k_ctrl
            if (ground and j > 3) or j > c.end_f:
                if ground and r.k_land_her is None:
                    r.k_land_her = f - r.f_a
                self._close(f, "landed" if ground else "end")
                return None
            if r.after == "dash":
                if j < c.dash_hold:
                    return self._send(r, f, M_DASH | back)
                return self._send(r, f, 0)
            if r.after == "B":
                return self._send(r, f, self._down(r, f, s, e, back, y))
            return self._send(r, f, 0)
        return None

    def _down(self, r: ClawRun, f: int, s: dict, e: dict, back: int, y: float) -> int:
        """Variant B: drift toward its back; the down slash when its body is below her in reach."""
        c = self.cfg
        hx = _sp.hero_x(s)
        tm = (s.get("hero") or {}).get("tm") or {}
        ready = float(tm.get("atk_cd") or 0.0) * 60.0 - (SEND_AHEAD - 1) <= 0.05
        y0, y1 = _tp.body_y(e)
        top = y1 - (_sp.FLOOR_Y - 1.56)
        if (len(r.ds) < c.ds_max and ready and abs(float(e["pos"][0]) - hx) <= c.ds_reach
                and 0.0 <= y - top <= c.ds_top and (not r.ds or f - r.f_a - r.ds[-1] > 6)):
            r.ds.append(f - r.f_a)
            return M_D | M_A | back
        return back

    def _send(self, r: ClawRun, f: int, m: int) -> int:
        r.sent.append((f - r.f_a, m))
        return m

    def abort(self, why: str) -> None:
        if self.run is not None:
            self._close(self.run.f_a + (self.run.sent[-1][0] if self.run.sent else 0), why)

    def active(self) -> bool:
        return self.run is not None

    def stats(self) -> dict:
        runs = self.done + ([self.run] if self.run is not None else [])
        out = dict(self.n)
        out["claw_runs"] = [{"f_a": r.f_a, "J": r.J, "kind": r.kind, "d0": r.d0, "why": r.why, "hop": r.hop_hold,
                             "press_rel": r.press_rel, "after": r.after, "y_press": r.y_press, "y_ray": r.y_ray,
                             "k_ctrl": r.k_ctrl, "hook": r.hook, "hits": r.hits, "hp": r.hp, "gap_ctrl": r.gap_ctrl,
                             "k_land_j": r.k_land_j, "u_land": r.u_land, "k_land_her": r.k_land_her, "ds": r.ds,
                             "end": r.end, "f_end": r.f_end,
                             "sent": [[k, m] for k, m in r.sent if m] [:40]} for r in runs]
        return out
