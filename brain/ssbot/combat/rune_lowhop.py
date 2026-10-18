"""The small runes with a low hop and slashes all through (task 1v1 SP8d; the person 2026-10-16: "for the small runes, if
the jump is timed precisely, you do not even need to jump higher than the Clapper and can slash the whole time";
forum.md 75).

SSBOT_FORUM_RUNE_LOWHOP (read by train.forum_planner_policy; since the SP8d A/B on with SSBOT_FORUM_V2, =0 off; one live
Clapper only): when
the Clapper (Song Heavy Sentry) enters Spell Antic the bot plays the cast as a script: on the ground in front of it,
side slashes on the 19-frame rhythm, and one jump per bomb that covers her, its press frame and hold length chosen so
her box bottom stays above that bomb's circle while it is lit and as low as that allows; slashes in the air on the
rhythm where the slash still meets its body. The planner takes over when she lands from the hop (or when the cast is
over and no bomb threatens her).

The facts (C:/ssbot/data/m2_play/sp8d, 1,005 live casts of the SP8a-c runs, game frames of 1/60 s, k from the Spell
Antic entry; C = the Cast 2 entry):
  timeline  Spell Antic 43-44 frames, Cast 1 6, Cast 2 at k 48-50 lasting 24-26, then Idle 16-17 (p50; to 40);
            the next move: Evade Scuttle 61 %, Slam Antic 18 %, Walk 8 %, Spell Antic 5 %.
  its body  Spell Antic 0-3: top 3.19 u above the floor, front 2.05 u from its centre; 4-7: 4.36 / 2.06; 8 on and
            Cast 1 and Cast 2 0-13: 4.78 / 1.84; Cast 2 14 on: 3.19 / 2.05; Idle 3.92 / 2.25.
  bombs     ring r's pair at x0 +- 4.2 r (x0 its x at C), centre y = its y - 3.8 (the top 2.83 u above the floor),
            circle r 2.166; ring r appears at C + 9.6 r (0 / 9-10 / 19-20 / 28-30), lights 20-21 frames after it
            appears (p5-p95), lit 6 frames (p95 7). So between x0 + 2.67 and x0 + 5.73 (her box's half width 0.25
            in) only ring 1 reaches her: one hop, timed to its appearance (C + 9-10).
  the hop   the kinematics model's ground jump per hold H (hero_wanderer_forum.json; its logged apex table agrees):
            the box bottom per frame j from the latched press (HOP_LO / HOP_HI: the lowest / highest of the timing
            lanes); H 12 peaks 3.55-3.67 u (below its head, 3.92), above 2.95 from j 11 to 22.
  the slash the side slash's lower edge is the Wanderer slash polygon's (attacks/wanderer.json) measured from her box
            centre: a press meets the body when that edge at the gap to its near edge is below its top (1,143 live
            presses: margin >= -0.1 hit 13 / 13, below -0.5 1 of 174).
  the default under v2 floats or jumps 4.8 u up (p50) at ring 1's light and misses its Idle body (126 presses in
            reach from 3.9-5.3 u up, 0 hits); 15 of 1,005 casts lost HP to a bomb (she was 0.4-2.3 u up).

The script (every mask for frame f + 2; k counts game frames from the antic entry on the game clock):
  stance  on the ground: walk into stand_lo .. stand_hi from its centre (centre to centre) and, from Cast 2 on, into
          x0_lo .. x0_hi from x0 (only ring 1 reaches there); stop dead inside. A side slash (attack 2 frames, the
          key toward it on the press frame) whenever our presses are slash_cd apart, the STATE's attack cooldown is
          over and the slash from her x meets its body box (x reach and the lower edge, spare).
  hop     planned on every tick once a bomb that covers her is seen (it appears unlit 20-21 frames before it
          lights): the lowest hold H in h_min .. h_max whose press frames P put her box bottom (the lowest lane) at
          least `margin` above that bomb's circle at her x over its whole lit window (+ pre / post frames) for at
          least `min_slack` choices of P; of those P the one with the most slashes that can still land by the landing
          (the highest lane; no slash on the Idle Clapper while the hold or a bomb window is on: a hit on the Idle
          Clapper starts its next move at once), then the middle. The jump held from P for H game frames, no second
          jump press (in the air it opens the umbrella); in the air the key toward it only to keep the slash's
          reach, never past x0_lo .. x0_hi while a bomb covers her.
  critical while the hold or a covering bomb's window is on, the script keeps the keys ahead of the slam playbook,
          the jump antic scripts and the evade chase (the policy does not call them then: they start a few frames
          later, from the air).
Abort (the planner decides again): HP lost, the Clapper gone or a second one alive, a jump cast's rune circle over her
stance, a start in the air that does not land before the hop. SP11-0 (SSBOT_FORUM_TWO_GUARD; step(guard=...)): with two
Clappers no start / abort ("guard", outside the critical window) when the other one's danger span (combat.two_play
guard_spans: its jump landing band, its big rune circle, its hammer, its body) meets her way to the stance or the stance
(SP10a / SP10c audits: the stance on one's cast in the other's big rune circle). Done: landed from the hop; the cast over without a
covering bomb; another script took the keys outside the critical window.

    lh = RuneLowHop()                                         # per episode: lh.reset()
    m = lh.step(f, s, ground, accepting, t_game, latch)       # the mask for frame f + 2, or None (the planner decides)
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

from ssbot.combat import cast_stab as _cs
from ssbot.combat import rune_bombs as _rb
from ssbot.combat import slam_play as _sp


def _on(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip() == "1"


# SP8d A/B (forum.md 75.4; b2c14cd, rnjb vs sp8lh, 16 episodes each, the same seeds: kill p50 21.6 -> 19.5 s, landed / s
# 1.027 -> 1.126 (90 % +0.034 .. +0.165), HP-hitless 16 = 16; the person's rule "the faster arm is the default"): unset,
# SSBOT_FORUM_RUNE_LOWHOP follows SSBOT_FORUM_V2 (on with v2, off without it); =0 turns it off (arm rnsp8d0).
ENABLED = _on("SSBOT_FORUM_RUNE_LOWHOP", "1" if _on("SSBOT_FORUM_V2") else "0")
CLAPPER = _sp.CLAPPER
CAST_ST = ("Spell Antic", "Cast 1", "Cast 2")
M_L, M_R, M_A, M_J = _sp.M_L, _sp.M_R, _sp.M_A, _sp.M_J
SEND_AHEAD = _sp.SEND_AHEAD
WALK_U = _sp.WALK_U
FLOOR = 3.0
HALF_W = 0.25              # her box's half width
HALF_H = 1.0395            # her box's half height (2.079 u)
R = _rb.R
SLASH_X = _sp.SLASH_X      # the side slash's x reach in front of her box centre (0.19 .. 3.12)
# the Wanderer side slash's lower edge (knowledge/1.0.30000/attacks/wanderer.json "normal", the higher of the two
# slashes), x in front of her box centre -> y from her box centre
SLASH_LOW = ((0.193, -0.563), (1.6933, -0.359), (2.8424, -0.0653), (3.1213, 0.298))
# its body (top above the floor, front from its centre) by Control state and state frame (sp8d body_profile)
BODY_IDLE = (3.92, 2.25)
BODY_TALL = (4.78, 1.84)
BODY_LOW = (3.19, 2.05)

# The ground hop: box bottom above the floor on frames j = 0.. after the latched press frame, per hold H (frames), the
# lowest / highest of the kinematics model's timing lanes (sp8d hop_model.py; the logged apex per hold in
# hero_wanderer_forum.json jump_heights agrees: H 11 3.22-3.54, 12 3.54-3.66, 13 3.66-3.94).
HOP_LO = {
    9: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.62, 2.67, 2.67, 2.65, 2.60, 2.60, 2.53, 2.43,
        2.32, 2.17, 2.01, 2.00, 1.81, 1.60, 1.36, 1.10, 0.81, 0.75, 0.49, 0.16, 0.02),
    10: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 2.97, 3.02, 3.02, 3.00, 2.95, 2.91, 2.83,
         2.72, 2.66, 2.52, 2.35, 2.26, 2.05, 1.83, 1.71, 1.45, 1.16, 1.00, 0.68, 0.33, 0.15, 0.02),
    11: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.32, 3.32, 3.33, 3.31, 3.27, 3.21,
         3.12, 3.07, 3.00, 2.87, 2.70, 2.52, 2.31, 2.18, 2.05, 1.79, 1.51, 1.23, 0.91, 0.68, 0.50, 0.12, 0.02),
    12: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.55, 3.55, 3.53, 3.48,
         3.42, 3.42, 3.32, 3.20, 3.06, 2.90, 2.71, 2.61, 2.47, 2.25, 1.99, 1.71, 1.40, 1.19, 0.96, 0.71, 0.32, 0.02),
    13: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.63, 3.67, 3.67, 3.65,
         3.60, 3.60, 3.52, 3.43, 3.30, 3.16, 2.99, 2.99, 2.80, 2.58, 2.34, 2.07, 1.78, 1.67, 1.46, 1.13, 0.77, 0.38,
         0.02),
    14: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 3.92, 3.96, 3.95,
         3.92, 3.87, 3.87, 3.79, 3.69, 3.57, 3.42, 3.25, 3.23, 3.05, 2.83, 2.59, 2.32, 2.03, 1.91, 1.70, 1.37, 1.00,
         0.62, 0.20, 0.02),
    15: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.18, 4.21,
         4.21, 4.17, 4.12, 4.12, 4.04, 3.94, 3.81, 3.66, 3.48, 3.45, 3.28, 3.06, 2.81, 2.54, 2.24, 2.11, 1.91, 1.58,
         1.21, 0.82, 0.41, 0.17, 0.02),
    16: (0.03, 0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.42,
         4.45, 4.44, 4.40, 4.34, 4.32, 4.23, 4.12, 4.02, 3.87, 3.69, 3.64, 3.43, 3.20, 3.01, 2.74, 2.44, 2.29, 2.02,
         1.67, 1.40, 1.01, 0.59, 0.33, 0.02),
}
HOP_HI = {
    9: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 2.97, 3.02, 3.02, 3.01, 2.97, 2.91, 2.83, 2.77,
        2.72, 2.59, 2.44, 2.26, 2.06, 1.96, 1.83, 1.58, 1.30, 1.00, 0.75, 0.56, 0.33, 0.02),
    10: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.32, 3.32, 3.33, 3.31, 3.27, 3.21, 3.12,
         3.12, 3.00, 2.87, 2.71, 2.52, 2.40, 2.31, 2.08, 1.82, 1.54, 1.23, 1.10, 0.91, 0.55, 0.17, 0.02),
    11: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.55, 3.55, 3.53, 3.48, 3.42,
         3.42, 3.32, 3.20, 3.06, 2.90, 2.71, 2.71, 2.49, 2.25, 2.05, 1.79, 1.51, 1.40, 1.06, 0.71, 0.50, 0.12, 0.02),
    12: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.63, 3.67, 3.67, 3.67, 3.65,
         3.60, 3.52, 3.43, 3.37, 3.30, 3.16, 2.99, 2.80, 2.61, 2.47, 2.34, 2.07, 1.78, 1.47, 1.19, 0.96, 0.77, 0.38,
         0.02),
    13: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 3.92, 3.96, 3.96, 3.95,
         3.92, 3.87, 3.79, 3.70, 3.64, 3.57, 3.42, 3.25, 3.05, 2.88, 2.73, 2.59, 2.32, 2.03, 1.71, 1.46, 1.22, 1.00,
         0.62, 0.20, 0.02),
    14: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.18, 4.21, 4.21,
         4.21, 4.17, 4.12, 4.04, 3.95, 3.90, 3.81, 3.66, 3.48, 3.28, 3.13, 2.98, 2.81, 2.54, 2.24, 1.93, 1.70, 1.46,
         1.21, 0.82, 0.41, 0.02),
    15: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.42, 4.45,
         4.45, 4.43, 4.39, 4.32, 4.23, 4.19, 4.12, 3.98, 3.82, 3.64, 3.45, 3.35, 3.20, 2.94, 2.66, 2.35, 2.11, 1.91,
         1.67, 1.29, 0.89, 0.47, 0.17, 0.02),
    16: (0.03, 0.38, 0.73, 1.08, 1.43, 1.77, 1.77, 2.12, 2.47, 2.82, 3.17, 3.49, 3.49, 3.79, 4.07, 4.32, 4.55, 4.64,
         4.64, 4.64, 4.61, 4.56, 4.49, 4.41, 4.39, 4.27, 4.12, 3.95, 3.76, 3.65, 3.54, 3.30, 3.03, 2.75, 2.44, 2.29,
         2.09, 1.73, 1.40, 1.01, 0.59, 0.02),
}


@dataclass
class HopCfg:
    stand_lo: float = 3.6        # the stance from its centre (u, centre to centre): walk out when nearer
    stand_hi: float = 4.6        # ... walk in when farther (its tall body's front 1.84 + the reach 3.12 - spare)
    x0_lo: float = 2.95          # from Cast 2 on, her x from x0 (its x at the Cast 2 entry): ring 0 reaches < 2.67
    x0_hi: float = 5.45          # ... ring 2 reaches > 5.73
    margin: float = 0.12         # u: her box bottom at least this above the bomb circle's top at her box's nearest x
    pre: int = 1                 # frames before the earliest predicted first lit frame ...
    post: int = 1                # ... and after the latest predicted last lit frame, also clear
    lead_lo: int = 20            # a bomb lights this many game frames after it appears (p5)
    lead_hi: int = 21            # ... (p95)
    dur: int = 7                 # lit frames at most (p95; p50 6)
    x_pad: float = 0.3           # a bomb covers her when |her x - its x| < R + her half width + this
    h_min: int = 9
    h_max: int = 16
    min_slack: int = 3           # a hold needs at least this many press frames that clear (else the next hold)
    slash_cd: int = 19           # own presses this many frames apart (the Wanderer cooldown 0.3 s = 18 + 1)
    reach_spare: float = 0.1     # the slash's x reach must overlap its body box by this much
    y_spare: float = 0.1         # ... and its lower edge must be this much below the body's top
    start_max: float = 10.5      # no start farther than this at the antic entry (u; walking in from there
    #                              reaches the band by antic frame ~44)
    gap_lo: float = 0.6          # in the air: no key toward it when her box centre is nearer its body's edge than
    #                              this (u) ...
    gap_hi: float = 2.0          # ... the key toward it when the gap is beyond this (t1, 5c7cbd8, gap_hi 2.6: the
    #                              descent's slash at j 24 met its Idle body from d <= 4.63 u in 9 of 9, from 4.64 on
    #                              in 2 of 14 - its evade starts then)
    k_max: int = 200             # the run ends this many frames after the antic entry at the latest
    land_wait: int = 50          # after the press: no landing by P + this -> hand back
    cast2_k: float = 49.5        # Cast 2 entry from the antic entry (p50; before it is seen)
    cast2_len: int = 24          # Cast 2's frames (its Idle from C + 24, p5)


def _num_env(c: HopCfg) -> HopCfg:
    """SSBOT_FORUM_RUNE_LOWHOP_SET="margin=0.15,stand_hi=4.4": trial overrides of the numbers above."""
    for kv in os.environ.get("SSBOT_FORUM_RUNE_LOWHOP_SET", "").replace(";", ",").split(","):
        if "=" not in kv:
            continue
        k, v = (x.strip() for x in kv.split("=", 1))
        if not hasattr(c, k):
            raise KeyError(f"SSBOT_FORUM_RUNE_LOWHOP_SET: unknown key {k!r}")
        cur = getattr(c, k)
        setattr(c, k, type(cur)(float(v)))
    return c


def slash_low(g: float) -> float:
    """The side slash's lower edge (y from her box centre) at x g in front of her box centre."""
    g = max(g, SLASH_LOW[0][0])
    for (x0, y0), (x1, y1) in zip(SLASH_LOW, SLASH_LOW[1:]):
        if g <= x1:
            return y0 + (y1 - y0) * (g - x0) / (x1 - x0)
    return SLASH_LOW[-1][1]


def bomb_top(by: float, dx: float) -> float:
    """The top of a bomb circle (centre y by) above the floor at her box's nearest x (her box centre dx from its
    centre); -inf when her box is clear of it sideways."""
    e = max(0.0, abs(dx) - HALF_W)
    if e >= R:
        return -math.inf
    return by + math.sqrt(R * R - e * e) - FLOOR


def body_at(st: str | None, kst: float) -> tuple[float, float]:
    """(top above the floor, front from its centre) of its body box in Control state st at state frame kst."""
    if st == "Spell Antic":
        return BODY_LOW if kst < 4 else ((4.36, 2.06) if kst < 8 else BODY_TALL)
    if st == "Cast 1":
        return BODY_TALL
    if st == "Cast 2":
        return BODY_TALL if kst < 14 else BODY_LOW
    return BODY_IDLE


def hop_plan(threats: list[tuple[int, int, float]], k_first: int, holds: range, min_slack: int, score=None
             ) -> dict | None:
    """The hop for threats [(w0, w1, thr)]: game frames w0 .. w1 (k) that need her box bottom >= thr (above the
    floor). Press frames P >= k_first. The lowest hold with >= min_slack clearing press frames (else the lowest with
    any): {"H", "P", "lo", "hi"} (lo .. hi the clearing presses), P the best by score(H, P) (higher better; ties: the
    middle), or None."""
    fallback = None
    for H in holds:
        lo_t = HOP_LO[H]
        ok = []
        for P in range(k_first, k_first + 60):
            good = True
            for w0, w1, thr in threats:
                j0, j1 = w0 - P, w1 - P
                if j0 < 0 or j1 >= len(lo_t) or any(lo_t[j] < thr for j in range(j0, j1 + 1)):
                    good = False
                    break
            if good:
                ok.append(P)
            elif ok:
                break
        if not ok:
            continue
        mid = 0.5 * (ok[0] + ok[-1])
        if score is not None:
            best = max(ok, key=lambda P: (score(H, P), -abs(P - mid)))
        else:
            best = min(ok, key=lambda P: abs(P - mid))
        plan = {"H": H, "P": int(best), "lo": ok[0], "hi": ok[-1]}
        if len(ok) >= min_slack:
            return plan
        if fallback is None:
            fallback = plan
    return fallback


@dataclass
class Hop:
    iid: object
    face: int                    # its facing (+1 right); she is in front of it
    f0: int                      # the STATE frame of the start
    ta: float                    # the antic entry on the clock (s)
    fa: int                      # the antic entry's STATE frame (f0 - its state time)
    d0: float                    # her x in front of its centre at the start (u)
    ground0: bool
    hp0: int
    phase: str = "stance"        # stance -> hop -> done / abort
    why: str = ""
    tc: float | None = None      # the Cast 2 entry on the clock
    x0: float | None = None      # its x at the Cast 2 entry (ring 0's x once seen)
    bombs: dict = field(default_factory=dict)    # entity iid -> {"x", "y", "a", "on", "off", "end"}
    plan: dict | None = None     # the hop being planned / committed
    P: int | None = None         # the committed press frame (k) and hold
    H: int | None = None
    k_land: int | None = None
    presses: list = field(default_factory=list)  # (k of the mask, air?, her x in front, predicted bottom)
    hits: list = field(default_factory=list)     # (k, src)
    sent: list = field(default_factory=list)     # (f, mask)
    ticks: int = 0
    k: int = 0
    late: int = 0                # ticks a covering bomb was due with no feasible hop
    plans: int = 0


class RuneLowHop:
    def __init__(self, cfg: HopCfg | None = None, two: bool = False):
        self.cfg = cfg or _num_env(HopCfg())
        # SP9a S3 (SSBOT_FORUM_TWO_CAST, combat.two_play): with two live Clappers the caster in Spell Antic nearest to
        # her in front; no start / hand back (outside the critical window) while the other one can reach her
        self.two = two
        self.run: Hop | None = None
        self.done: list[Hop] = []
        self._seen: set = set()
        self.n_cast = 0
        self.why_not: dict = {}
        self._runes: dict = {}
        self.guard_f: list = []            # SSBOT_FORUM_TWO_GUARD: frames of the casts not started for it

    def reset(self) -> None:
        self.run = None
        self.done = []
        self._seen = set()
        self.n_cast = 0
        self.why_not = {}
        self._runes = {}
        self.guard_f = []

    # ---- bookkeeping ----

    def observe(self, f: int, s: dict) -> None:
        """Every tick (whichever script runs): the jump cast rune circles' first frame and lit state."""
        self._rune_threats(f, s)

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

    def active(self) -> bool:
        return self.run is not None and self.run.phase in ("stance", "hop")

    def critical(self) -> bool:
        """The hop's hold or a covering bomb's window is on: the script keeps the keys ahead of the other scripts."""
        r = self.run
        if r is None or r.phase != "hop" or r.P is None:
            return False
        if r.k < r.P + r.H + 1:
            return True
        return any(w1 >= r.k for _, w1, _ in self._threat_windows(r, None))

    def abort(self, why: str) -> None:
        if self.active():
            self._close("abort", why)

    def yield_to(self, s: dict) -> None:
        """Another script sends the keys this tick (outside the critical window): the run ends."""
        if self.active():
            self._close("done", "other")

    def _close(self, phase: str, why: str = "") -> None:
        r = self.run
        if r is not None:
            r.phase, r.why = phase, r.why or why
            self.done.append(r)
        self.run = None

    def stats(self) -> dict:
        from collections import Counter
        out = Counter({"casts": self.n_cast})
        runs = self.done + ([self.run] if self.run is not None else [])
        for r in runs:
            out["runs"] += 1
            out["hops"] += r.P is not None
            out["presses"] += len(r.presses)
            out["air_presses"] += sum(1 for p in r.presses if p[1])
            out["hits_in_run"] += len(r.hits)
            out["late"] += r.late > 0
            out[f"end_{r.phase}_{r.why}"] += 1
            if r.H is not None:
                out[f"hold_{r.H}"] += 1
        for k, v in self.why_not.items():
            out[f"no_{k}"] += v
        res = dict(out)
        res["hop_runs"] = [self._rec(r) for r in runs]
        if self.guard_f:
            res["guard_nostart_f"] = list(self.guard_f)
        return res

    @staticmethod
    def _rec(r: Hop) -> dict:
        return {"f0": r.f0, "fa": r.fa, "d0": r.d0, "ground0": r.ground0, "x0": r.x0,
                "k_c2": None if r.tc is None else round((r.tc - r.ta) * 60.0, 1),
                "bombs": {str(i): b for i, b in r.bombs.items() if b.get("cover")},
                "plan": r.plan, "P": r.P, "H": r.H, "k_land": r.k_land, "presses": r.presses, "hits": r.hits,
                "late": r.late, "plans": r.plans, "end": r.phase, "why": r.why, "ticks": r.ticks, "k": r.k}

    # ---- the script ----

    def step(self, f: int, s: dict, ground: bool, accepting: bool = True, t_game: float | None = None,
             latch=None, skip: frozenset | None = None, guard: list | None = None) -> int | None:
        """The mask for frame f + 2 while the script runs, else None. t_game: the game clock (s; Stamp.t_game_s);
        latch: m -> the key mask the oracle's hold filter latches at f + 2 when m is sent for it (None: m)."""
        t = f / 60.0 if t_game is None else float(t_game)
        e = self._pick(s) if self.two else _sp.clapper(s)
        if skip and e is not None and e.get("iid") in skip and not self.critical():
            # SP9c (combat.two_play's antic switch): its cast is left alone (she switched to the other one)
            if self.run is not None and self.run.iid in skip:
                self._close("abort", "asw")
            return None
        st, tin = _sp.control(e)
        h = s.get("hero") or {}
        hp = int(h.get("health") or 0)
        r = self.run
        if r is not None:
            if hp < r.hp0:
                self._close("abort", "hurt")
                return None
            gone = e is None or e.get("iid") != r.iid
            two = not gone and not self._n_ok(s)
            new = not gone and st == "Spell Antic" and abs((t - tin) - r.ta) * 60.0 > 30
            if (gone or two or new) and self.critical():
                # t1 (5c7cbd8): an air slash killed it at P + 7, the run ended, the hold was cut at 8 frames and its
                # ring-1 bomb (the bombs stay) hit her 7 frames later: the hold and the bomb window run on
                r.k = int(round((t - r.ta) * 60.0)) + SEND_AHEAD
                self._observe_cast(r, s, None, None, 0.0, t, r.k - SEND_AHEAD)
                m = M_J if r.k - r.P < r.H else 0
                r.sent.append((f, m))
                r.ticks += 1
                r.why = r.why or ("gone (hop on)" if gone else "two (hop on)" if two else "new cast (hop on)")
                return m
            if gone:
                self._close("abort", "gone")
                return None
            if two:
                self._close("abort", "two")
                return None
            if new:
                self._close("done", "new cast")          # a new cast: its own run below
                r = None
            elif self.two and len(_sp.clappers(s)) == 2 and not self.critical():
                from ssbot.combat import two_play as _tp
                why = _tp.other_danger(s, r.iid, self._hx(s))
                if why is not None:
                    self._close("abort", "other")
                    return None
                if guard is not None and e is not None and self._guarded(s, e, r.face, guard):
                    self._close("abort", "guard")
                    return None
        if r is None:
            if e is None or st != "Spell Antic":
                return None
            ta = t - tin
            key = (e.get("iid"), round(ta * 60.0))
            if any(k_[0] == key[0] and abs(k_[1] - key[1]) <= 3 for k_ in self._seen):
                return None
            self._seen.add(key)
            self.n_cast += 1
            face = 1 if e.get("flipX") else -1
            d0 = (_sp.hero_x(s) - float(e["pos"][0])) * face
            why = None
            if not self._n_ok(s):
                why = "two"
            elif d0 <= 0:
                why = "behind"
            elif d0 > self.cfg.start_max:
                why = "far"
            elif hp <= 0:
                why = "dead"
            elif self._rune_over(f, s, float(e["pos"][0]), face):
                why = "rune"
            elif self.two and len(_sp.clappers(s)) == 2:
                from ssbot.combat import two_play as _tp
                if _tp.other_danger(s, e.get("iid"), self._hx(s)) is not None:
                    why = "other"
                elif guard is not None and self._guarded(s, e, face, guard):
                    why = "guard"
                    self.guard_f.append(f)          # SSBOT_FORUM_TWO_GUARD: the no-start frames (stats)
            if why is not None:
                self.why_not[why] = self.why_not.get(why, 0) + 1
                return None
            r = self.run = Hop(iid=e.get("iid"), face=face, f0=f, ta=ta, fa=int(f - round(tin * 60.0)),
                               d0=round(d0, 3), ground0=bool(ground), hp0=hp)
        k_now = int(round((t - r.ta) * 60.0))
        r.k = k_now + SEND_AHEAD
        self._observe_cast(r, s, e, st, tin, t, k_now)
        for ev in s.get("ev") or ():
            d = ev.get("d") or {}
            if ev.get("k") == "hit" and d.get("type_key") == CLAPPER:
                dealt = d.get("dealt", d.get("amount"))
                if dealt is None or float(dealt) > 0:
                    r.hits.append((k_now, str(d.get("src"))))
        m = self._step(r, f, s, e, st, tin, ground, accepting, latch)
        if m is None:
            return None
        r.sent.append((f, m))
        r.ticks += 1
        return m

    def _n_ok(self, s: dict) -> bool:
        n = len(_sp.clappers(s))
        return n == 1 or (n == 2 and self.two)

    def _pick(self, s: dict) -> dict | None:
        """two=True: the run's Clapper; else (two live) the one in Spell Antic nearest to her with her in front; else
        the first."""
        cs = _sp.clappers(s)
        if self.run is not None:
            return next((e for e in cs if e.get("iid") == self.run.iid), None)
        if len(cs) == 2:
            hx = _sp.hero_x(s)
            sp_ = [e for e in cs if _sp.control(e)[0] == "Spell Antic"
                   and (hx - float(e["pos"][0])) * (1 if e.get("flipX") else -1) > 0]
            if sp_:
                return min(sp_, key=lambda e: abs(float(e["pos"][0]) - hx))
        return _sp.clapper(s)

    def _guarded(self, s: dict, e: dict, face: int, guard: list) -> str | None:
        """SSBOT_FORUM_TWO_GUARD: the other Clapper's danger span kind over her way to the stance or the stance."""
        from ssbot.combat import two_play as _tp
        cx = float(e["pos"][0])
        a, b = cx + face * self.cfg.stand_lo, cx + face * self.cfg.stand_hi
        hx = _sp.hero_x(s)
        return _tp.guard_hit(guard, min(a, b, hx), max(a, b, hx), own=e.get("iid"))

    def _rune_over(self, f: int, s: dict, cx: float, face: int) -> bool:
        a = cx + face * self.cfg.stand_lo
        b = cx + face * self.cfg.stand_hi
        hx = _sp.hero_x(s)
        lo, hi = min(a, b, hx), max(a, b, hx)
        return any(x < hi and y > lo for x, y in self._rune_threats(f, s))

    def _observe_cast(self, r: Hop, s: dict, e: dict, st: str | None, tin: float, t: float, k_now: int) -> None:
        if st == "Cast 2" and r.tc is None and e is not None:
            r.tc = t - tin
            if r.x0 is None:
                r.x0 = float(e["pos"][0])
        cur = {}
        for iid, bx, by, lit in _rb.bomb_ents(s.get("ents")):
            cur[iid] = lit
            b = r.bombs.get(iid)
            if b is not None and abs(b["x"] - bx) > 0.3:
                b = None                                    # a pooled object placed anew
            if b is None:
                b = r.bombs[iid] = {"x": round(bx, 3), "y": round(by, 3), "a": k_now, "on": None, "off": None,
                                    "end": False}
                if r.x0 is not None and abs(bx - r.x0) < 0.6 and (r.tc is not None and k_now <= (r.tc - r.ta) * 60
                                                                  + 3):
                    r.x0 = float(bx)                        # ring 0: the exact x0
            if lit:
                if b["on"] is None:
                    b["on"] = k_now
                b["off"] = k_now
            elif b["on"] is not None:
                b["end"] = True
        for iid, b in r.bombs.items():
            # gone after it lit: spent; gone unlit (the pool may drop it for a frame or two): spent only once its
            # latest lit window is past
            if iid not in cur and (b["on"] is not None or k_now > b["a"] + self.cfg.lead_hi + self.cfg.dur + 2):
                b["end"] = True

    def _hx(self, s: dict) -> float:
        h = s.get("hero") or {}
        vx = float((h.get("vel") or [0.0, 0.0])[0])
        return _sp.hero_x(s) + vx * SEND_AHEAD / 60.0

    def _threat_windows(self, r: Hop, hx: float | None, xs: tuple = ()) -> list[tuple[int, int, float]]:
        """[(w0, w1, thr)] of the bombs still to hurt that cover her (her x hx and the xs she may be at): game frames
        (k) her box bottom must stay at or above thr (u above the floor)."""
        c = self.cfg
        out = []
        for b in r.bombs.values():
            if b["end"]:
                continue
            if hx is None:
                if not b.get("cover"):
                    continue
                dx = b.get("dx", 0.0)
            else:
                dxs = [abs(x - b["x"]) for x in (hx,) + tuple(xs)]
                dx = min(dxs)
                if dx >= R + HALF_W + c.x_pad:
                    continue
                b["cover"] = True
                b["dx"] = round(dx, 3)
            if b["on"] is not None:
                w0, w1 = b["on"], b["on"] + c.dur - 1
            else:
                w0, w1 = b["a"] + c.lead_lo, b["a"] + c.lead_hi + c.dur - 1
            thr = bomb_top(b["y"], max(0.0, dx - c.x_pad)) + c.margin
            out.append((w0 - c.pre, w1 + c.post, thr))
        return out

    def _body(self, r: Hop, k: int) -> tuple[float, float, str]:
        """Its body (top, front, state) predicted at frame k (from the antic entry)."""
        c = self.cfg
        kc = (r.tc - r.ta) * 60.0 if r.tc is not None else c.cast2_k
        if k < kc - 6:
            return (*body_at("Spell Antic", k), "Spell Antic")
        if k < kc:
            return (*BODY_TALL, "Cast 1")
        if k < kc + c.cast2_len:
            return (*body_at("Cast 2", k - kc), "Cast 2")
        return (*BODY_IDLE, "Idle")

    def _body_now(self, st: str | None, tin: float) -> tuple[float, float, bool]:
        """Its body (top, front) on the frame a slash pressed for this tick's mask meets it (state frame + SEND_AHEAD
        + 1), from the STATE's Control state (the lower top where the state may turn over), and whether it will be in
        Idle then."""
        c = self.cfg
        kst = tin * 60.0 + SEND_AHEAD + 1
        if st in CAST_ST:
            top, front = body_at(st, kst)
            if st == "Cast 2" and kst >= c.cast2_len:
                return min(top, BODY_IDLE[0]), max(front, BODY_IDLE[1]), True
            return top, front, False
        if st == "Idle":
            return BODY_IDLE[0], BODY_IDLE[1], True
        return BODY_IDLE[0], BODY_IDLE[1], False

    def _slash_meets(self, gap: float, bottom: float, top: float) -> bool:
        """The side slash from her box (bottom above the floor) meets a body box gap u ahead (her box centre to its
        near edge) whose top is top: x reach and the lower edge."""
        c = self.cfg
        if gap > SLASH_X[1] - c.reach_spare:
            return False
        return bottom + HALF_H + slash_low(max(gap, 0.0)) < top - c.y_spare

    def _score(self, r: Hop, k_ready: int, gap: float, w_end: int):
        """score(H, P): the slashes that can land from k_ready to the hop's landing (the highest lane), the
        rhythm slash_cd, no slash on the Idle Clapper before w_end (the hold and the bomb windows)."""
        c = self.cfg

        def score(H: int, P: int) -> int:
            hi_t = HOP_HI[H]
            end = P + len(hi_t)
            n, t = 0, k_ready
            idle_from = max(w_end, P + H + 1)
            while t < end:
                j = t + 1 - P
                bot = 0.03 if j < 0 else (hi_t[j] if j < len(hi_t) else 0.03)
                top, _, bst = self._body(r, t + 1)
                if bst == "Idle" and t + 1 < idle_from:
                    t += 1
                    continue
                if self._slash_meets(gap, bot, top):
                    n += 1
                    t += c.slash_cd
                else:
                    t += 1
            return n
        return score

    def _step(self, r: Hop, f: int, s: dict, e: dict, st: str | None, tin: float, ground: bool, accepting: bool,
              latch) -> int | None:
        c = self.cfg
        k = r.k                                           # the frame this tick's mask lands on
        h = s.get("hero") or {}
        tm = h.get("tm") or {}
        cx = float(e["pos"][0]) + float((e.get("vel") or [0.0, 0.0])[0]) * SEND_AHEAD / 60.0
        hx = self._hx(s)
        d = (hx - cx) * r.face                            # her x in front of its centre on the mask's frame
        toward = M_R if -r.face > 0 else M_L
        away = M_L if toward == M_R else M_R
        bottom = float((h.get("box") or [0, FLOOR, 0, 0])[1]) - FLOOR
        if k > c.k_max:
            self._close("done", "timeout")
            return None
        # the hop committed: hold, air slashes, steer, land
        if r.phase == "hop":
            j = k - r.P
            if ground and j > 4:
                r.k_land = k
                self._close("done", "landed")
                return None
            if j > c.land_wait:
                self._close("done", "no landing")
                return None
            m = M_J if j < r.H else 0
            m |= self._air_keys(r, s, e, st, tin, k, d, cx, hx, toward, away, tm, j)
            return m
        # stance: the cast over and nothing covers her -> the planner
        cast = st in CAST_ST
        xs = self._stand_xs(r, cx)
        thr = self._threat_windows(r, hx, xs)
        if not cast and not thr:
            self._close("done", "over")
            return None
        if not cast and st not in ("Idle", None):
            self._close("done", "next")                   # its next move began (no hop was due)
            return None
        # the hop: plan on every tick once a covering bomb is seen
        prev = r.sent[-1][1] if r.sent else 0
        cont = M_A | toward if (r.presses and k - r.presses[-1][0] == 1 and prev & M_A) else 0
        if thr:
            if not ground:
                if min(w0 for w0, _, _ in thr) - k < 12:
                    # a covering bomb lights soon and she is in the air (a start in the air, a knock-back): the hop
                    # cannot be pressed - the planner (its bomb forecast) decides
                    self._close("abort", "air")
                    return None
            else:
                last = r.presses[-1][0] if r.presses else -99
                cd = float(tm.get("atk_cd") or 0.0)
                k_ready = max(k, last + c.slash_cd, k + int(math.ceil(max(0.0, cd * 60.0 - (SEND_AHEAD - 1)))))
                key = [(int(a), int(b), round(x, 2)) for a, b, x in thr]
                plan = r.plan
                if plan is None or plan["thr"] != key or plan["P"] < k:
                    # (re)plan when the covering bombs change (a new one, a light seen) or the press was missed; a
                    # plan is kept otherwise (its slack shrinks as the frames pass)
                    body_front = self._body(r, k)[1]
                    gap = max(0.0, d - body_front)
                    w_end = max(w1 for _, w1, _ in thr)
                    plan = hop_plan(thr, k, range(c.h_min, c.h_max + 1), c.min_slack,
                                    score=self._score(r, k_ready, min(gap, SLASH_X[1] - 0.5), w_end))
                    if plan is not None:
                        r.plans += 1
                        plan = r.plan = {**plan, "k": k, "thr": key}
                if plan is None:
                    r.late += 1
                else:
                    if plan["P"] <= k:
                        ok = latch is None or bool(int(latch(M_J)) & M_J)
                        if ok:
                            r.P, r.H = k, plan["H"]
                            r.phase = "hop"
                            m = M_J | cont
                            if not cont and self._slash_ok(r, s, e, st, tin, k, d, tm, air=False, j=0):
                                r.presses.append((k, False, round(d, 2), 0.0))
                                m |= M_A | toward
                            return m
        # the ground stance: a slash when it meets its body, else walk into the band
        if cont:
            return cont                                   # the slash's second frame
        if self._slash_ok(r, s, e, st, tin, k, d, tm, air=not ground, j=None):
            r.presses.append((k, not ground, round(d, 2), round(bottom, 2)))
            return M_A | toward
        lo, hi = c.stand_lo, c.stand_hi
        x0d = None if r.x0 is None else (hx - r.x0) * r.face
        clip = str((h.get("anim") or {}).get("clip") or "")
        if "Sprint" in clip or "Dash" in clip:
            return 0                                      # a held key would keep the sprint going (into its body)
        if d > hi + 0.5 * WALK_U or (x0d is not None and x0d > c.x0_hi):
            return toward
        if d < lo - 0.5 * WALK_U or (x0d is not None and x0d < c.x0_lo):
            return away
        return 0

    def _stand_xs(self, r: Hop, cx: float) -> tuple:
        """The x she may stand at before the bombs light (the band's ends), for the cover check."""
        c = self.cfg
        a = cx + r.face * c.stand_lo
        b = cx + r.face * c.stand_hi
        if r.x0 is not None:
            a = r.x0 + r.face * max(c.x0_lo, min(c.x0_hi, c.stand_lo + (cx - r.x0) * r.face))
            b = r.x0 + r.face * max(c.x0_lo, min(c.x0_hi, c.stand_hi + (cx - r.x0) * r.face))
        return (a, b)

    def _slash_ok(self, r: Hop, s: dict, e: dict, st: str | None, tin: float, k: int, d: float, tm: dict,
                  air: bool, j: int | None) -> bool:
        """A side slash pressed on frame k (the mask's) meets its body on k + 1: our rhythm, the attack ready, the x
        reach and the lower edge (her bottom on k + 1: the hop's highest lane when j is given, else now + her vy)."""
        c = self.cfg
        if r.presses and k - r.presses[-1][0] < c.slash_cd:
            return False
        cd = tm.get("atk_cd")
        if cd is not None and float(cd) * 60.0 - (SEND_AHEAD - 1) > 0.05:
            return False
        h = s.get("hero") or {}
        clip = str((h.get("anim") or {}).get("clip") or "")
        if any(x in clip for x in ("Dash", "Sprint", "Skid")):
            return False
        top, front, idle = self._body_now(st, tin)
        if idle and r.phase == "hop" and self.critical():
            return False                                  # a hit starts its next move: not inside the hop's window
        span = None
        for col in e.get("colliders") or ():
            if col.get("name") == CLAPPER and col.get("enabled") and col.get("verts_world"):
                xs = col["verts_world"][0::2]
                span = (float(min(xs)), float(max(xs)))
                break
        cx = float(e["pos"][0])
        if span is None:
            span = (cx - front, cx + front) if r.face < 0 else (cx - front, cx + front)
        near = span[1] if r.face > 0 else span[0]        # its front edge (she is in front)
        hx = _sp.hero_x(s)
        gap = (hx - near) * r.face
        if gap < -0.3:
            return False
        if j is not None and r.H is not None:
            jj = j + 1
            bot = HOP_HI[r.H][jj] if 0 <= jj < len(HOP_HI[r.H]) else 0.03
        else:
            b0 = float((h.get("box") or [0, FLOOR, 0, 0])[1]) - FLOOR
            vy = float((h.get("vel") or [0.0, 0.0])[1])
            bot = max(0.0, b0 + vy * (SEND_AHEAD + 1) / 60.0) if air else b0
        return self._slash_meets(gap, bot, top)

    def _air_keys(self, r: Hop, s: dict, e: dict, st: str | None, tin: float, k: int, d: float, cx: float, hx: float,
                  toward: int, away: int, tm: dict, j: int) -> int:
        """In the hop: the slash on the rhythm where it meets its body (its second frame), else the key toward it
        only when the gap to its body is beyond gap_hi (and never past x0_lo .. x0_hi while a bomb covers her)."""
        c = self.cfg
        prev = r.sent[-1][1] if r.sent else 0
        if r.presses and k - r.presses[-1][0] == 1 and prev & M_A:
            return M_A | toward
        if self._slash_ok(r, s, e, st, tin, k, d, tm, air=True, j=j):
            r.presses.append((k, True, round(d, 2), round(HOP_HI[r.H][min(j + 1, len(HOP_HI[r.H]) - 1)], 2)))
            return M_A | toward
        front = self._body(r, k)[1]
        gap = d - front
        covered = any(w1 >= k for _, w1, _ in self._threat_windows(r, None))
        x0d = None if r.x0 is None else (hx - r.x0) * r.face
        if gap > c.gap_hi and not (covered and x0d is not None and x0d - WALK_U < c.x0_lo):
            return toward
        if gap < c.gap_lo and not (covered and x0d is not None and x0d + WALK_U > c.x0_hi):
            return away
        return 0
