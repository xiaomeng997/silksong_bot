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

    def step(self, f: int, s: dict, ground: bool, accepting: bool, t: float | None = None) -> int | None:
        if not ENABLED:
            return None
        cs = _sp.clappers(s)
        now = {e.get("iid"): _sp.control(e)[0] for e in cs}
        prev, self._prev = self._prev, now
        h = s.get("hero") or {}
        if not (h.get("box") or h.get("pos")):
            return None
        if self.run is None:
            for e in cs:
                st = now.get(e.get("iid"))
                if st in ("Jump Antic", "Cast Slam Antic") and prev.get(e.get("iid")) not in JUMP_ANTIC:
                    self._start(f, s, e, ground, accepting)
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
