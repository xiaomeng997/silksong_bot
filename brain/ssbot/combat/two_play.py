"""Two Clappers, SP9a (task 1v1 SP9a, Forum_W_w13; the spec C:/ssbot/data/m2_play/switch/answer.txt section 5 S1-S6,
human_two/answer.txt R2-R7 and R9, buddy/answer.txt R1-R3; forum.md 76).

Every rule has its own switch; since the SP9a A/B (594bb71, 32 episodes per arm: kills 10 -> 36 Clappers, landed / s
0.70 -> 1.27, HP hits / min 5.67 -> 4.46) each follows SSBOT_FORUM_V2 when unset, =0 off; with all =0 nothing here runs
and every decision is the one before (arm rnsp9a0).
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

SP9b (task 1v1 SP9b, forum.md 77; the person 2026-10-16: "for the corner escape jump, SP9 does both the corner and the
switch, compares them live, and the faster becomes the default"; the spec switch/answer.txt 2f / 4 / 5 S4, buddy/answer.txt
section 4 and R4, human_two R8). F's escape jump: F evades with its back within ~6 u of the wall behind it (Evade Scuttle's
entry -> Escape Jump, jump / jump cast alternating, no buddy check; the STATE shows Idle -> Jump Antic / Cast Slam Antic):
the first STATE that shows F (the Clapper she is on: the nearer one, within ESC d_u) entering a jump antic with its centre
within ESC back_u of the wall behind it starts an EscRun (TwoPlay.esc). B is locked through F's antic and flight (the flag
from the antic to Slam 2: jump 1.21-1.43 s, jump cast 1.63-1.85 s), F's tail is Slam 2 + Slam Recover (~20 frames).
  SSBOT_FORUM_TWO_CORNER       arm A (default off): slash the antic (combat.cast_stab's JB_CORNER antic script, two
                               Clappers allowed for F's escape jump), the corner stance (4.4 u in front) through the
                               antic, the way under to the behind spot from its take-off (cast_stab's corner way under),
                               its back slashed in Slam 2 / Slam Recover (the planner, JUMP_BEHIND's landed stance), L2's
                               target held on F; then off the wall: no hit on F in its Idle (a hit there makes it attack
                               at once with her pinned at the wall: the person's corner hits, buddy section 4) and, the
                               jump slam, once its evade coin has passed (Idle + coin_f) with F still idle and her
                               >= hop_b_min behind it: the hop over it (the jump held H, the key toward the open side from
                               d0, the air dash at jd: hop_over_table, worst-case clearance >= 0.6 u over its body); the
                               jump cast: behind it, no hit, until its rune circle burst (the circle reaches 0.6 u behind
                               its landing), then the normal play.
  SSBOT_FORUM_TWO_WALLSWITCH   arm B (default off): at F's escape-jump antic L2's target is B (when B is not in a jump
                               move and no rune circle lies over it), held until B's next move or F's tail end + a margin;
                               no hit on B while F's flag is on (a hit then is cancelled: B re-enters Idle and its evade
                               coin fires 0.25 s later, faster than the slash cooldown), then the deciding hit on B in F's
                               tail: the side slash on the first STATE showing F's landing (Slam 2) when it meets B's body
                               (walk in when it reaches by the tail's end) - B decides (a close move within 8.3 u) and F,
                               deciding after its tail, sees B attacking and cancels.
  SSBOT_FORUM_TWO_ESC_SET      "back_u=6,coin_f=18": trial overrides of the EscCfg numbers.

    two = TwoPlay()                                   # per episode: two.reset()
    m = two.step(f, s, ground, accepting, focus, t)   # IdleHit / Opening / SP9b: the mask for frame f + 2, or None
    prefs = two.space(prefs, s, t)                    # TWO_SPACE's stance
    v = two.esc_view()                                # SP9b: the escape run for L2 (gauntlet) and cast_stab, or None
"""
from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field, replace

from ssbot.combat import cast_stab as _cs
from ssbot.combat import slam_play as _sp


def _on(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip() == "1"


# SP9a A/B (594bb71, forum.md 76; the person's rule "the faster arm is the default", two Clappers: more landed per s and
# kills, not more HP hits per min): the promoted switches below follow SSBOT_FORUM_V2 when unset (on with v2), =0 off
# (arm rnsp9a0 = the default with every two-Clapper switch off)
_V2 = "1" if _on("SSBOT_FORUM_V2") else "0"
CHASE = _on("SSBOT_FORUM_TWO_CHASE", _V2)
IDLEHIT = _on("SSBOT_FORUM_TWO_IDLEHIT", _V2)
CAST = _on("SSBOT_FORUM_TWO_CAST", _V2)
SPACE = _on("SSBOT_FORUM_TWO_SPACE", _V2)
OPEN = _on("SSBOT_FORUM_TWO_OPEN", _V2)
# SP9b (forum.md 77): the escape jump at a wall, two arms; default off until the live A/B
ESC_CORNER = _on("SSBOT_FORUM_TWO_CORNER")
ESC_SWITCH = _on("SSBOT_FORUM_TWO_WALLSWITCH")
ESC = ESC_CORNER or ESC_SWITCH
ANY = IDLEHIT or SPACE or OPEN or ESC   # the policy's TwoPlay object (CHASE / CAST live in their own scripts)

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

# ---- SP9b: the escape jump ----
ESC_ANTIC = ("Jump Antic", "Cast Slam Antic")
ESC_PRE = ESC_ANTIC + ("Cast Slam Antic 2",)
FLIGHT_ST = ("Jump Aim", "Cast Jump", "Jump", "Air")
LAND_ST = ("Slam 2", "Slam Effects?", "Slam Recover")
MOVE_ST = ("Slam Antic", "Spell Antic", "Jump Antic", "Cast Slam Antic", "Evade Scuttle")
M_J, M_DASH = _sp.M_J, _sp.M_DASH


@dataclass
class EscCfg:
    back_u: float = 6.2       # its centre to the wall behind it at the antic's first STATE (the escape line 5.83 - 6.06 u,
    #                           switch answer section 1; the first STATE may show it a frame into the jump antic)
    d_u: float = 8.3          # she within this of it (|dx|, centre to centre): inside its Slam Range Close Range cannot
    #                           pick a jump, so a jump antic there is the escape jump
    # arm A (TWO_CORNER): off the wall
    exit: int = 1             # 1: the hop over it (the jump slam) after its evade coin; 0: stay (the person's own play)
    coin_f: int = 17          # its Idle's evade coin fires at 0.25 s (15 frames) when the entry rolled it: from here on
    #                           an Idle F stays idle until 1.15 s (69 frames) unless hit
    hop_b_min: float = 2.5    # the hop only with her centre this far behind its centre (hop_over_table: worst-case
    #                           clearance over its turned Idle body 0.63 u at 2.5, >= 1.0 u from 2.75)
    hop_b_max: float = 5.25   # ... and not farther (the table's range)
    hop_end_j: int = 75       # the hop ends here at the latest (it lands at j 51-57)
    rune_wait_f: int = 100    # the jump cast: no hit on F until its rune circle burst (lit, then unlit) or this long
    #                           after its landing (lit 63-86 frames after the landing)
    end_f: int = 150          # the corner run ends this long after the landing at the latest
    # arm B (TWO_WALLSWITCH)
    sw_tail_f: int = 22       # F's tail: Slam 2 + Slam Recover, 19-20 frames from the landing to its Idle
    sw_end_f: int = 60        # the switch run ends this long after F's landing at the latest


def _esc_cfg() -> EscCfg:
    """SSBOT_FORUM_TWO_ESC_SET="back_u=6,coin_f=18": trial overrides of the EscCfg numbers."""
    c = EscCfg()
    for kv in os.environ.get("SSBOT_FORUM_TWO_ESC_SET", "").replace(";", ",").split(","):
        if "=" not in kv:
            continue
        k, v = (x.strip() for x in kv.split("=", 1))
        if not hasattr(c, k):
            raise KeyError(f"SSBOT_FORUM_TWO_ESC_SET: unknown key {k!r}")
        setattr(c, k, type(getattr(c, k))(float(v)))
    return c


# The hop over the landed Clapper from the corner (C:/ssbot/data/m2_play/sp9b/hop_over_table.json, kinematics
# rollouts with every timing lane, her standing b u behind its centre, its Idle body turned to her: x -2.25 .. +1.34,
# top 3.92 u): b -> (jump held H frames, the key toward the open side from d0, the air dash at jd; frames from the
# latched press); worst-case clearance 0.63 u at b 2.5, 1.0-1.06 u from 2.75; she lands ~5.6-6.6 u on its open side
# 51-57 frames after the press
HOP_TABLE = ((2.5, 20, 16, 24), (2.75, 28, 16, 28), (3.0, 28, 16, 26), (3.25, 28, 14, 26), (3.5, 28, 14, 26),
             (3.75, 28, 12, 26), (4.0, 28, 10, 26), (4.25, 28, 8, 26), (4.5, 28, 6, 26), (4.75, 28, 4, 26),
             (5.0, 28, 2, 26))


def hop_plan(b: float) -> tuple[int, int, int] | None:
    """The hop's (H, d0, jd) for her b u behind its centre (the table's nearest row), None outside the table."""
    if b < HOP_TABLE[0][0] - 1e-6 or b > HOP_TABLE[-1][0] + 0.25 + 1e-6:
        return None
    row = min(HOP_TABLE, key=lambda r: abs(r[0] - b))
    return row[1], row[2], row[3]


def back_room(e: dict) -> float:
    """Its centre to the wall behind it (against its facing), u."""
    cx = float(e["pos"][0])
    return (cx - WALL_L) if face_of(e) > 0 else (WALL_R - cx)


@dataclass
class EscRun:
    iid: object                # F
    other: object              # B
    kind: str                  # "jump" (the jump slam) / "cast" (the jump cast)
    f_a: int                   # the STATE frame that first showed the antic
    k_a: int                   # its antic frame then
    x0: float                  # F's x, facing (+1 right: + = its open side, away from the wall) and back room then
    face: int
    back0: float
    rel0: float                # her x in front of it (u, centre to centre)
    o_st: str | None           # B's state and distance from her then
    o_d: float
    mode: str | None           # "corner" / "switch" / None (the arm did not take it: why)
    hp0: int = 0
    why: str = ""
    phase: str = "antic"       # antic / flight / landed / idle / done
    f_take: int | None = None
    f_land: int | None = None  # F's landing (Slam 2's first frame, from its state time)
    f_idle: int | None = None  # F's first Idle after the landing
    u_land: float | None = None  # her x along its facing from its centre at the landing (- = the corner side)
    x_land: float | None = None  # F's x at the landing
    hits_f: list = field(default_factory=list)    # (frame - f_a, phase) of landed hits on F / on B
    hits_b: list = field(default_factory=list)
    hp: list = field(default_factory=list)        # frames (- f_a) of HP losses while the run lasts
    exit: str | None = None    # corner: hop / stay / front / moved / rune / near / far / danger / end
    hop: dict | None = None    # corner: {"f0", "b", "plan", "j_end", "u_end", "end"}
    press: dict | None = None  # switch: {"f" (- f_land), "d", "b_st", "hit" (- f_land), "b_next", "k_next"}
    rune: dict = field(default_factory=dict)      # the jump cast's circle: {"seen", "lit", "burst"} (frames - f_land)
    walk: int = 0
    f_end: int | None = None
    end: str = ""


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
        # SP9b: the escape run (F's jump at the wall) and the finished ones
        self.ecfg = _esc_cfg() if ESC else EscCfg()
        self.esc: EscRun | None = None
        self.esc_done: list[EscRun] = []
        self.esc_n: Counter = Counter()
        self._esc_hop_f: int | None = None   # the hop's latched press frame (mask frame j = 0)
        self._esc_hop_plan: tuple | None = None

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
        antics = []
        for e in _sp.clappers(s):
            iid = e.get("iid")
            st, tin = _sp.control(e)
            # an Idle (re-)entry this tick: the first frame showing Idle, or its state time starting again (a hit ->
            # Dmg Attack -> Close Range -> CANCEL -> Idle in one frame while the buddy attacks)
            pst = self.prev.get(iid)
            if st == "Idle" and (pst is None or pst[0] != "Idle" or tin + 0.5 / 60.0 < pst[1]):
                self.entry[iid] = pst is not None and pst[0] == "Idle"
            if ESC and st in ESC_ANTIC and (pst is None or pst[0] not in ESC_PRE):
                antics.append(e)
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
        if ESC:
            self._esc_observe(f, s, t, hx, antics)
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
        if ESC and self.esc is not None:
            em = self._esc_step(f, s, ground, accepting)
            if em is not None:
                return em
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
        if ESC:
            v = self.esc_view()
            if v is not None and iid in v["no_hit"]:
                r.why = r.why or "esc"             # SP9b: no hit on it now (the corner's wait / F's lock)
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

    # ---- SP9b: the escape jump (TWO_CORNER / TWO_WALLSWITCH) ----

    def esc_view(self) -> dict | None:
        """The running escape jump for L2 (gauntlet) and cast_stab: {"iid" (F), "other" (B), "mode", "phase", "kind",
        "hold" (L2's target to keep), "no_hit" (iids whose hits do not count / no IdleHit), "corner_aim" (F's antic:
        the stance in reach), "after_land"}; None without a run the arm took."""
        r = self.esc
        if r is None or r.mode is None:
            return None
        v = {"iid": r.iid, "other": r.other, "mode": r.mode, "phase": r.phase, "kind": r.kind, "back0": r.back0,
             "back_u": self.ecfg.back_u, "after_land": r.f_land is not None, "corner_aim": False,
             "no_hit": frozenset()}
        if r.mode == "corner":
            v["hold"] = r.iid
            v["corner_aim"] = r.phase == "antic"
            if r.phase == "idle" and r.exit in (None, "hop"):
                v["no_hit"] = frozenset({r.iid})          # its Idle: a hit makes it attack her at once, pinned
        else:
            v["hold"] = r.other
            if r.f_land is None:
                v["no_hit"] = frozenset({r.other})        # F's flag on: a hit on B is cancelled (its coin then)
        return v

    def _esc_observe(self, f: int, s: dict, t: float, hx: float | None, antics: list) -> None:
        cs = _sp.clappers(s)
        hp = int((s.get("hero") or {}).get("health") or 0)
        if self.esc is not None:
            self._esc_update(f, s, hx, hp, cs)
        if self.esc is None and antics and len(cs) == 2 and hx is not None:
            for e in antics:
                self._esc_start(f, s, e, cs, hx, hp)
                if self.esc is not None:
                    break

    def _esc_start(self, f: int, s: dict, e: dict, cs: list, hx: float, hp: int) -> None:
        c = self.ecfg
        st, tin = _sp.control(e)
        o = next(x for x in cs if x.get("iid") != e.get("iid"))
        cx, ox = float(e["pos"][0]), float(o["pos"][0])
        back = back_room(e)
        d, do = abs(hx - cx), abs(hx - ox)
        self.esc_n["jump_antics"] += 1
        if back > c.back_u:
            self.esc_n["no_wall"] += 1
            return
        if d > c.d_u or d > do:
            self.esc_n["no_near"] += 1
            return
        mode, why = None, ""
        if ESC_CORNER:
            mode = "corner"
        elif ESC_SWITCH:
            why = self._sw_block(f, s, o, hx)
            mode = None if why else "switch"
        face = face_of(e)
        self.esc = EscRun(iid=e.get("iid"), other=o.get("iid"), kind="jump" if st == "Jump Antic" else "cast", f_a=f,
                          k_a=int(round(tin * 60.0)), x0=round(cx, 3), face=face, back0=round(back, 2),
                          rel0=round((hx - cx) * face, 2), o_st=_sp.control(o)[0], o_d=round(do, 2), mode=mode,
                          hp0=hp, why=why)
        self.esc_n["runs"] += 1
        self.esc_n[f"mode_{mode}"] += 1
        if why:
            self.esc_n[f"no_switch_{why}"] += 1

    def _sw_block(self, f: int, s: dict, o: dict, hx: float) -> str:
        """Why B cannot be the target now ("" when it can): in a jump move (its landing aims at her), or a rune circle
        (lit or to come) over the way to it."""
        st = _sp.control(o)[0]
        if st in JUMP_ST:
            return "other jumping"
        ox = float(o["pos"][0])
        lo, hi = min(hx, ox), max(hx, ox)
        if any(a < hi and b > lo for a, b in self._rune_threats(f, s)):
            return "rune"
        return ""

    def _esc_update(self, f: int, s: dict, hx: float | None, hp: int, cs: list) -> None:
        r = self.esc
        c = self.ecfg
        for ev in s.get("ev") or ():
            d = ev.get("d") or {}
            if ev.get("k") == "hit" and d.get("type_key") == CLAPPER and (d.get("dealt") is None
                                                                            or float(d.get("dealt")) > 0):
                tgt = d.get("ent") or d.get("iid")
                if tgt == r.iid:
                    r.hits_f.append((f - r.f_a, r.phase))
                elif tgt == r.other:
                    r.hits_b.append((f - r.f_a, r.phase))
                    if r.press is not None and r.press.get("f") is not None and r.press.get("hit") is None \
                            and r.f_land is not None:
                        r.press["hit"] = f - r.f_land
        if hp < r.hp0:
            r.hp.append(f - r.f_a)
        r.hp0 = hp
        e = clapper_by(s, r.iid)
        o = clapper_by(s, r.other)
        if e is None:
            self._esc_close(f, "F dead")
            return
        if o is None and r.mode == "switch":
            self._esc_close(f, "B dead")
            return
        st, tin = _sp.control(e)
        cx = float(e["pos"][0])
        k_st = int(round(tin * 60.0))
        if r.phase == "antic" and st in FLIGHT_ST:
            r.phase, r.f_take = "flight", f - k_st
        if r.phase in ("antic", "flight") and st not in ESC_PRE + FLIGHT_ST:
            r.phase = "landed"
            r.f_land = f - k_st if st == "Slam 2" else f
            r.x_land = cx
            if hx is not None:
                r.u_land = round((hx - cx) * r.face, 2)
        if r.phase == "landed" and st not in LAND_ST:
            r.phase = "idle"
            r.f_idle = f - k_st if st == "Idle" else f
        if r.kind == "cast" and r.f_land is not None:
            # its own big rune circle (centre 6.48 u in front of the landing along its jump facing)
            for lo, hi, _iid, lit in _cs.rune_spans(s):
                if abs(0.5 * (lo + hi) - (r.x_land + r.face * 6.48)) <= 4.0:
                    r.rune.setdefault("seen", f - r.f_land)
                    if lit:
                        r.rune.setdefault("lit", f - r.f_land)
                    elif "lit" in r.rune:
                        r.rune.setdefault("burst", f - r.f_land)
        if r.mode == "switch":
            if r.f_land is not None and o is not None:
                ost = _sp.control(o)[0]
                if ost in MOVE_ST and f > r.f_land:
                    if r.press is None:
                        r.press = {"f": None}
                    r.press.update(b_next=ost, k_next=f - r.f_land)
                    self._esc_close(f, "B move")
                elif f - r.f_land > c.sw_end_f:
                    self._esc_close(f, "end")
        elif r.mode == "corner":
            if self._esc_hop_f is None:
                if r.exit is not None and r.exit != "hop":
                    self._esc_close(f, r.exit)
                elif r.f_land is not None and f - r.f_land > c.end_f:
                    self._esc_close(f, "end")
        elif r.f_land is not None and f - r.f_land > c.sw_end_f:
            self._esc_close(f, "end")                       # the arm did not take it (stats only)

    def _esc_close(self, f: int, why: str) -> None:
        r = self.esc
        if r is not None:
            r.f_end, r.end = f - r.f_a, why
            self.esc_done.append(r)
            self.esc_n[f"end_{why}"] += 1
        self.esc = None
        self._esc_hop_f = None

    def _esc_step(self, f: int, s: dict, ground: bool, accepting: bool) -> int | None:
        r = self.esc
        if r is None or r.mode is None:
            return None
        if r.mode == "corner":
            return self._corner_step(f, s, ground, accepting)
        return self._switch_step(f, s, ground, accepting)

    def _corner_step(self, f: int, s: dict, ground: bool, accepting: bool) -> int | None:
        """Arm A's way off the wall (module docstring): the jump slam's hop over F after its coin moment."""
        r = self.esc
        c = self.ecfg
        if self._esc_hop_f is not None:
            return self._hop_keys(f, s, ground)
        if r.phase not in ("landed", "idle") or r.exit is not None:
            return None
        e = clapper_by(s, r.iid)
        if e is None:
            return None
        st, tin = _sp.control(e)
        hx = _sp.hero_x(s)
        u = (hx - float(e["pos"][0])) * r.face
        if c.exit == 0:
            r.exit = "stay"
            return None
        if u > -0.5:
            r.exit = "front"                               # not in the corner: nothing to leave
            return None
        if r.kind == "cast":
            # behind it, no hit (esc_view), until its rune circle burst
            if "burst" in r.rune or f - r.f_land > c.rune_wait_f:
                r.exit = "rune"
            return None
        if r.phase == "landed":
            return None                                    # its back slashed (the planner)
        if st != "Idle":
            r.exit = "moved"
            return None
        k_idle = f - r.f_idle + SEND_AHEAD                 # the mask's frame from its Idle entry
        if k_idle < c.coin_f:
            return None                                    # the planner, no hit on it
        if k_idle > c.coin_f + 15:
            r.exit = "late"                                # (another script had the keys): its Idle may end mid-hop
            return None
        b = -u
        plan = hop_plan(b) if c.hop_b_min <= b <= c.hop_b_max else None
        if plan is None:
            r.exit = "near" if b < c.hop_b_min else "far"
            return None
        if not (ground and accepting) or any(x in str(((s.get("hero") or {}).get("anim") or {}).get("clip") or "")
                                             for x in NO_ATK_CLIPS):
            if k_idle > c.coin_f + 12:
                r.exit = "late"
            return None
        why = other_danger(s, r.iid, hx, self._rune_threats(f, s))
        if why is not None:
            r.exit = "danger"
            r.why = r.why or why
            return None
        r.exit = "hop"
        r.hop = {"f0": f - r.f_land, "k_idle": k_idle, "b": round(b, 2), "plan": list(plan), "j_end": None,
                 "u_end": None, "end": None}
        self._esc_hop_f = f + SEND_AHEAD
        self.esc_n["hops"] += 1
        return self._hop_keys(f, s, ground)

    def _hop_keys(self, f: int, s: dict, ground: bool) -> int | None:
        r = self.esc
        c = self.ecfg
        j = f + SEND_AHEAD - self._esc_hop_f
        H, d0, jd = r.hop["plan"]
        e = clapper_by(s, r.iid)
        u = None if e is None else round((_sp.hero_x(s) - float(e["pos"][0])) * r.face, 2)
        hurt = bool(r.hp) and r.hp[-1] >= r.hop["f0"] + (r.f_land - r.f_a)
        if (j > 8 and ground) or j > c.hop_end_j or hurt:
            r.hop.update(j_end=j, u_end=u, end="hurt" if hurt else "landed" if ground else "end")
            self._esc_close(f, "hop")
            return None
        toward = M_R if r.face > 0 else M_L
        m = 0
        if j < H:
            m |= M_J
        if j >= d0:
            m |= toward
        if jd and jd <= j < jd + 2:
            m |= M_DASH
        return m

    def _switch_step(self, f: int, s: dict, ground: bool, accepting: bool) -> int | None:
        """Arm B's deciding hit on B in F's tail (module docstring): from F's landing (its flag off) the side slash on B
        when it meets B's body (B in Idle: only Idle reacts to a hit), the walk in when that reaches it by the tail's
        end."""
        r = self.esc
        c = self.ecfg
        if r.f_land is None:
            return None
        pr = r.press
        if pr is not None and pr.get("pf") is not None:
            sec = self._second(f)
            return sec if sec is not None and self._press_f == pr["pf"] else None
        k = f - r.f_land
        if pr is None and self.idle is not None and self.idle.iid == r.other and self.idle.k_press is not None:
            r.press = {"f": k, "by": "idlehit", "b_st": "Idle"}   # IdleHit pressed on B's Idle (re-)entry already
            return None
        if k > c.sw_tail_f:
            if pr is None:
                r.press = {"f": None, "why": "late"}
            return None
        o = clapper_by(s, r.other)
        e = clapper_by(s, r.iid)
        if o is None or e is None or not accepting:
            return None
        if _sp.control(o)[0] != "Idle":
            if pr is None:
                r.press = {"f": None, "why": f"b {_sp.control(o)[0]}"}
            return None
        if not ground:
            return None
        hxw = self._xw(s)
        # F's landing hammer (Slam Collider 2, 0.67 - 7.76 u in front of it): no press from in front of it
        st_f = _sp.control(e)[0]
        if st_f in ("Slam 2", "Slam Effects?") and 0.0 < (hxw - float(e["pos"][0])) * face_of(e) < 8.3:
            return None
        ox = float(o["pos"][0])
        look = 1 if ox > hxw else -1
        toward = M_R if look > 0 else M_L
        span = body_span(o)
        if slash_meets(hxw, look, span):
            if not self._atk_ready(s):
                return 0 if k < c.sw_tail_f else None
            if not self._facing(s, look):
                return toward
            r.press = {"f": k, "pf": f, "d": round(abs(hxw - ox), 2), "b_st": "Idle"}
            self.esc_n["sw_press"] += 1
            return self._press(f, toward)
        gap = (span[0] - hxw) if look > 0 else (hxw - span[1])
        if k + max(0.0, gap - (_sp.SLASH_X[1] - 0.15)) / WALK_U <= c.sw_tail_f:
            r.walk += 1
            return toward
        return None

    def esc_yield(self, f: int) -> None:
        """Another script took the keys: a running hop ends."""
        r = self.esc
        if r is not None and self._esc_hop_f is not None:
            r.hop.update(j_end=f + SEND_AHEAD - self._esc_hop_f, end="yield")
            self._esc_close(f, "hop")

    def esc_stats(self) -> dict:
        runs = self.esc_done + ([self.esc] if self.esc is not None else [])
        out = dict(self.esc_n)
        out["esc_runs"] = [{"f_a": r.f_a, "kind": r.kind, "mode": r.mode, "why": r.why, "back0": r.back0,
                            "rel0": r.rel0, "k_a": r.k_a, "o_st": r.o_st, "o_d": r.o_d,
                            "take": None if r.f_take is None else r.f_take - r.f_a,
                            "land": None if r.f_land is None else r.f_land - r.f_a,
                            "idle": None if r.f_idle is None else r.f_idle - r.f_a, "u_land": r.u_land,
                            "hits_f": r.hits_f, "hits_b": r.hits_b, "hp": r.hp, "exit": r.exit, "hop": r.hop,
                            "press": {k: v for k, v in (r.press or {}).items() if k != "pf"} if r.press else None,
                            "rune": r.rune, "walk": r.walk, "f_end": r.f_end, "end": r.end} for r in runs]
        return out

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
        if ESC:
            res["esc"] = self.esc_stats()
        return res


def intro_keys(s: dict) -> int:
    """SSBOT_FORUM_TWO_OPEN: the harness's key mask in the wave-start intro (the load -> the wave's activation): left
    while her x is right of OPEN_INTRO_X, else none."""
    h = s.get("hero") or {}
    if not (h.get("box") or h.get("pos")) or not h.get("hero_accepting_input", True):
        return 0
    return M_L if _sp.hero_x(s) > OPEN_INTRO_X else 0

