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
  SSBOT_FORUM_TWO_WALLSWITCH   arm B (since its A/B on with SSBOT_FORUM_V2, =0 off): at F's escape-jump antic L2's target is B (when B is not in a jump
                               move and no rune circle lies over it), held until B's next move or F's tail end + a margin;
                               no hit on B while F's flag is on (a hit then is cancelled: B re-enters Idle and its evade
                               coin fires 0.25 s later, faster than the slash cooldown), then the deciding hit on B in F's
                               tail: the side slash on the first STATE showing F's landing (Slam 2) when it meets B's body
                               (walk in when it reaches by the tail's end) - B decides (a close move within 8.3 u) and F,
                               deciding after its tail, sees B attacking and cancels.
  SSBOT_FORUM_TWO_ESC_SET      "back_u=6,coin_f=18": trial overrides of the EscCfg numbers.

SP9c (task 1v1 SP9c, forum.md 78; the spec switch/answer.txt 2b-2h, 3 and 5 S7; the person's plan notes of 2026-10-16
"switch target when the focus starts an antic near its wall", "refined switch timing"; an A/B arm only - the model says
every antic-switch variant lands fewer hits). F's close slam / cast antic near its wall: the first STATE that shows F (the
Clapper she is on: the nearer one, inside its Slam Range, so Close Range picked the move) entering Slam Antic / Spell
Antic with B idle or walking on F's open side, B >= sep_min from F (a slam: >= sep_slam, its hammer covers her path to B
when nearer), and the wall test (trig 0: its back <= back_u 8.1 u; trig 1, the person's refined trigger: its back after
this move (disp_*) - the next walk-back walk_back - knock x hits_after < pred_line, one slide) starts an AswRun.
  SSBOT_FORUM_TWO_ANTICSWITCH  (default off): not on F's first attack of the wave (the opening's A1: punish it);
                               L2's target is B from the antic (lock-in: no switch back before the first hit on B after
                               F's flag-off, B's own move, or end_f); the slam playbook / the low hop leave F's move alone;
                               a walk script (the dash held into the sprint, released inside Sprint Grace, only when the
                               run alone is late for the hold point / a slam's hammer line x0 + hammer_u by hammer_k): the
                               hold point hold_b u short of B (outside its Slam Range: t1, entering it during F's lock let
                               an idle B's evade coin fire at once) until step_spare frames before F's predicted flag-off,
                               then the walk to the press point (B's near edge - reach_in); no planner hit on B while F's
                               flag is on (a hit on B then is cancelled: B re-enters Idle and rolls its evade coin), but the
                               script's press on B's Idle (re-)entry within lock_win frames (the hit lands before the coin
                               at 0.25 s: "re-hit B inside 0.25 s of each Idle re-entry during F's lock"); from F's flag-off
                               (Slam 2 / Cast 2) the deciding side slash on B when it meets B's body (a slam: not from
                               inside the hammer before Slam Recover) - B decides a close move, F after its tail sees B
                               attacking. A cast: F's small-rune rings reach her at B (the bomb at her x lights ~1.3-1.7 s
                               after F's antic) - the run keeps a bomb phase after the lock-in to F's flag-off + bomb_f:
                               the hop over each covering bomb of F's row (rune_lowhop's hop_plan on the bombs seen at her
                               x, the unlit leftovers of an earlier row ignored), standing still until its press; while it
                               is due / held the script keeps the keys ahead of the other scripts (asw_critical).
  SSBOT_FORUM_TWO_ASW_SET      "trig=1,back_u=7.5": trial overrides of the AswCfg numbers.

    two = TwoPlay()                                   # per episode: two.reset()
    m = two.step(f, s, ground, accepting, focus, t)   # IdleHit / Opening / SP9b / SP9c: the mask for frame f + 2, or None
    prefs = two.space(prefs, s, t)                    # TWO_SPACE's stance
    v = two.esc_view()                                # SP9b / SP9c: the run for L2 (gauntlet) and cast_stab, or None
    skip = two.asw_skip()                             # SP9c: F while the antic switch runs (the slam playbook, the low hop)
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
# SP9b (forum.md 77): the escape jump at a wall, two arms. A/B (555bf98, 2 rounds x 16 per arm, block design, the same
# seeds; the person's rule "the faster becomes the default"): the switch (arm B) was the faster - landed / s 1.267 ->
# 1.303, Clappers killed 36 -> 38, HP-loss hits / min 4.69 -> 3.99 vs the SP9a default (corner 1.284 / 35 / 4.38): since
# then TWO_WALLSWITCH follows SSBOT_FORUM_V2 when unset (=0 off; arm rnsp9b0); TWO_CORNER stays default off (=1 on:
# the corner takes F's escape jump before the switch)
ESC_CORNER = _on("SSBOT_FORUM_TWO_CORNER")
ESC_SWITCH = _on("SSBOT_FORUM_TWO_WALLSWITCH", _V2)
ESC = ESC_CORNER or ESC_SWITCH
# SP9c (forum.md 78): the close-only antic switch, an A/B arm (default off, =1 on)
ASW = _on("SSBOT_FORUM_TWO_ANTICSWITCH")
ANY = IDLEHIT or SPACE or OPEN or ESC or ASW   # the policy's TwoPlay object (CHASE / CAST live in their own scripts)

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
    # (t1 fix) F's jump aims at her x at its Jump Aim (lands 5 u short of her, on its side): the landing hammer (Slam
    # Collider 2, 0.67 - 7.76 u in front of the landing) and the jump cast's circle (landing + 6.48 u, r 7.19) cover the
    # ground in front of her there. So before the aim she holds sw_hold_j (jump slam) / sw_hold_c (jump cast) u short
    # of B's centre, after the aim she goes to the landing + sw_safe_j / sw_safe_c (outside the hammer / the circle +
    # her half width + margin) and no nearer to B than sw_b_gap (its Idle front 2.25 + 0.23 + 0.2); a switch only when
    # B is on the open side at least sw_hold + 0.5 u from her
    sw_hold_j: float = 7.0
    sw_hold_c: float = 12.0
    sw_safe_j: float = 9.0       # (t3: 8.3 left her 7.63 u in front of the real landing once: the hammer)
    sw_safe_c: float = 14.5
    sw_f_front: float = 4.5      # the hold never nearer to F's centre than this (t3: B walked in, the hold point moved
    #                              back and she walked into F's body): nearer -> the run hands back ("b came")
    sw_b_gap: float = 2.7


def _esc_cfg() -> EscCfg:
    """SSBOT_FORUM_TWO_ESC_SET="back_u=6,coin_f=18": trial overrides of the EscCfg numbers."""
    return _set_cfg(EscCfg(), "SSBOT_FORUM_TWO_ESC_SET")


def _set_cfg(c, env: str):
    for kv in os.environ.get(env, "").replace(";", ",").split(","):
        if "=" not in kv:
            continue
        k, v = (x.strip() for x in kv.split("=", 1))
        if not hasattr(c, k):
            raise KeyError(f"{env}: unknown key {k!r}")
        setattr(c, k, type(getattr(c, k))(float(v)))
    return c


# ---- SP9c: the antic switch ----
ASW_ANTIC = {"Slam Antic": "slam", "Spell Antic": "cast"}
ASW_ON_ST = {"slam": ("Slam Antic", "Slam 0", "Slam 1", "Slam Effects?"), "cast": ("Spell Antic", "Cast 1")}
ASW_HAMMER_ST = ("Slam 0", "Slam 1", "Slam Effects?", "Slam 2")     # its hammer (Slam Collider 1 / 2) may be out


@dataclass
class AswCfg:
    trig: int = 0             # 0: T8.1 - F's back <= back_u; 1: the person's refined trigger - pred_back < pred_line
    back_u: float = 8.1       # (switch answer section 3: slide 5.40 + one idle movement 2.08 = 7.5, her 1.5x = 8.1)
    d_u: float = 8.3          # Close Range picked the move: she within its Slam Range (|dx| <= d_u, |dy| <= dy_u)
    dy_u: float = 3.9
    sep_slam: float = 16.0    # a slam only with F-B >= this (the hammer covers her path to B when nearer: 2f)
    sep_min: float = 4.0      # B at least this far from F (x; Avoid Type within 4 u)
    # trig 1 (the person 2026-10-16 "refined switch timing"; the lead: its wall distance after this move + the next
    # walk-back 2.1 u + her knock-back 0.48 u per hit below one slide 5.4 u): its back after this move = back0 +
    # disp_<kind> (its x along its facing from the antic to its Idle, her hits in it included: SP9b A/B close focus
    # antics p50 slam +3.12 .. +3.24 (the lunge), cast -1.44 .. -1.62) - walk_back - knock x hits_after
    pred_line: float = 5.4
    walk_back: float = 2.1
    knock: float = 0.48
    disp_slam: float = 3.1
    disp_cast: float = -1.5
    hits_after: float = 1.0
    # F's move (frames from its antic's first frame; SP9b A/B close focus antics p10 / 50 / 90)
    k_off_slam: int = 56      # Slam 2 entry (its flag off) 55 / 56 / 66
    k_off_cast: int = 49      # Cast 2 entry 48 / 49 / 50
    tail_slam: int = 20       # Slam 2 + Slam Recover to its Idle (k_idle - k_off p50 21)
    tail_cast: int = 25       # Cast 2 to its Idle (p50 25-26)
    hammer_u: float = 12.3    # a slam: her centre beyond x0 + this along F's facing from hammer_k until its Slam
    #                           Recover (Slam Collider 2's farthest point from x0 p90 11.96, + her half width 0.25 + 0.1)
    hammer_k: int = 50        # (Slam Collider 1 from 0.85 s p10 = antic frame 51)
    hold_b: float = 8.8       # the hold point this far from B's centre (outside its Slam Range 8.3 + 0.25 + 0.25)
    reach_in: float = 2.7     # the press point: her centre this far from B's near body edge (the slash reach 3.12)
    gap_b: float = 2.75       # never nearer to B's centre than this
    step_spare: int = 4       # the step-in from the hold point starts this many frames before F's predicted flag-off
    #                           (0.5 u to B's Slam Range: she enters it about at the flag-off)
    dash_min: float = 3.5     # a ground dash only with at least this far to go (u; it moves 3.27 u in 7 frames)
    far_slack: int = 8        # the start: the hold point reached by the step-in + this many frames (else "far")
    first: int = 1            # no switch on F's first attack move of the wave (the opening's A1: punish it; c3 is
    #                           17-19 u away - switch answer section 4)
    release_lag: float = 2.0  # the dash held into the ground sprint: released when her travel in this many frames at her
    #                           speed reaches the target (cast_stab T2's closed loop) ...
    grace_f: int = 10         # ... at the latest this many frames into the sprint (Sprint Grace: no skid)
    combo_f: int = 10         # no press this many frames after the sprint (DASHCOMBO_WINDOW 0.15 s: the dash combo)
    end_f: int = 90           # lock-in: the run ends this long after F's flag-off at the latest
    bomb_f: int = 95          # a cast: the run's bomb phase (the hop over F's small-rune bombs at her x) lasts to F's
    #                           flag-off + this (ring 6, 25 u from it, lit by Cast 2 + 58 + 21 + 7)
    bomb_lead: int = 30       # a covering bomb's window this close (frames): plan the hop, stand still until its press
    x_pad: float = 0.3        # a bomb covers her when |her x - its x| < its radius + her half width + this
    margin: float = 0.12      # her box bottom at least this above the bomb circle's top (rune_lowhop's HopCfg)
    lock_win: int = 10        # F's lock: the press on B's Idle (re-)entry only up to this many frames after it (the
    #                           hit lands 3-4 frames after the press's STATE: before the coin at 15)


def _asw_cfg() -> AswCfg:
    """SSBOT_FORUM_TWO_ASW_SET="trig=1,back_u=7.5": trial overrides of the AswCfg numbers."""
    return _set_cfg(AswCfg(), "SSBOT_FORUM_TWO_ASW_SET")


def pred_back(c: AswCfg, back0: float, kind: str) -> float:
    """The refined trigger's prediction: F's back after this move, the next walk-back and her knock-back (AswCfg)."""
    disp = c.disp_slam if kind == "slam" else c.disp_cast
    return back0 + disp - c.walk_back - c.knock * c.hits_after


@dataclass
class AswRun:
    iid: object                # F
    other: object              # B
    kind: str                  # "slam" / "cast"
    f_a: int                   # the STATE frame that first showed the antic
    k_a: int                   # its antic frame then (the STATE's lag)
    ta: float                  # the antic's entry on the game clock
    x0: float                  # F's x, facing (+1 right; B is on that side), back room, the prediction
    face: int
    back0: float
    pred: float
    sep0: float                # F-B |dx|
    rel0: float                # her x in front of F (u, centre to centre)
    o_st: str                  # B's state and |dx| from her
    o_d: float
    mode: str | None           # "aswitch" / None (not taken: why)
    hp0: int = 0
    why: str = ""
    phase: str = "go"          # go (F's flag on) / tail (F's flag off .. its Idle) / after (until the lock-in ends)
    f_off: int | None = None   # F's flag-off (the STATE frame that first showed Slam 2 / Cast 2)
    k_off: int | None = None   # ... its antic frame
    f_rec: int | None = None   # a slam: its Slam Recover (the hammer is gone)
    f_idle: int | None = None
    hits_f: list = field(default_factory=list)    # (frame - f_a, phase) of landed hits on F / on B
    hits_b: list = field(default_factory=list)
    b_idle: list = field(default_factory=list)    # frames (- f_a) of B's Idle (re-)entries
    b_evade: int | None = None                     # frame (- f_a) of B's Evade Scuttle in the run
    hp: list = field(default_factory=list)
    presses: list = field(default_factory=list)   # (frame - f_a, kind, |dx| to B)
    dash: list = field(default_factory=list)      # antic frames k of the dash-sprints
    dash_end: int | None = None                    # the STATE frame she had control again after the last one
    o_prev: str | None = None                      # B's state on the last tick
    lock_end: str | None = None                    # the lock-in's end (a cast's run then keeps its bomb phase)
    f_lock: int | None = None
    bombs: dict = field(default_factory=dict)      # small-rune bombs: iid -> {"x", "y", "a", "on", "end", "stale"}
    k_now: int = 0
    hop_P: int | None = None                       # the bomb hop: its press (antic frame k) and hold
    hop_H: int = 0
    hops: list = field(default_factory=list)       # (P, H, w0, w1)
    pending: bool = False                          # a covering bomb's window within bomb_lead (the hop to plan)
    k_line: int | None = None  # a slam: the antic frame she was first beyond the hammer line
    k_hold: int | None = None  # the antic frame she first reached the hold / press point
    hit_b: int | None = None   # the first landed hit on B from F's flag-off on (frames - f_off; < 0: in F's lock)
    b_next: str | None = None  # B's next move (state) and its frame - f_off
    k_next: int | None = None
    tx: float | None = None    # the target x this tick
    walk: int = 0
    f_end: int | None = None
    end: str = ""


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
    aim_hx: float | None = None  # her x at F's Jump Aim (its first flight STATE) and F's predicted landing x from it
    land_pred: float | None = None
    u_now: float | None = None   # her x along its facing from its centre now
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
        self._sw_stance_x: float | None = None  # arm B's stance this tick (F's flag on)
        # SP9c: the antic switch
        self.acfg = _asw_cfg() if ASW else AswCfg()
        self.asw: AswRun | None = None
        self.asw_done: list[AswRun] = []
        self.asw_n: Counter = Counter()
        self._asw_dash: dict | None = None    # the dash held into the sprint: {"f0", "dir", "rel", "ctl"}
        self._n_att: Counter = Counter()      # iid -> its attack antics seen (slam / cast / jump / jump cast)
        self._asw_prev = 0                    # its last mask

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
        asw_antics = []
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
            if ASW and st in ASW_ANTIC and (pst is None or pst[0] != st):
                asw_antics.append(e)
            if ASW and (st in ASW_ANTIC or st in ESC_ANTIC) and (pst is None or pst[0] != st):
                self._n_att[iid] += 1
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
        if ASW:
            self._asw_observe(f, s, t, hx, asw_antics)
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
             two_enc: bool = False, latch=None) -> int | None:
        """The mask for frame f + 2 (IdleHit, the Opening, SP9b / SP9c), or None (the planner). latch: m -> the key mask
        the oracle's hold filter latches at f + 2 when m is sent for it (SP9c's dash; None: m)."""
        if ASW and self.asw is not None:
            am = self._asw_step(f, s, ground, accepting, t, latch)
            if am is not None:
                self._asw_prev = am
                return am
            self._asw_prev = 0
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
        if ESC or ASW:
            v = self.esc_view()
            if v is not None and iid in v["no_hit"]:
                r.why = r.why or "esc"             # SP9b / SP9c: no hit on it now (the corner's wait / F's lock)
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
        the stance in reach), "after_land"}; None without a run the arm took. SP9c: the antic switch's run (mode
        "aswitch") the same way."""
        if ASW and self.asw is not None and self.asw.mode is not None and self.asw.lock_end is None:
            return self._asw_view()
        r = self.esc
        if r is None or r.mode is None:
            return None
        v = {"iid": r.iid, "other": r.other, "mode": r.mode, "phase": r.phase, "kind": r.kind, "back0": r.back0,
             "back_u": self.ecfg.back_u, "after_land": r.f_land is not None, "corner_aim": False,
             "no_hit": frozenset()}
        if r.mode == "corner":
            v["hold"] = r.iid
            v["corner_aim"] = r.phase == "antic"
            # (t2) she in the corner (behind F) after its landing: L2 keeps F above the slammer rule (B's slam sent her
            # through F's body twice) and F's dash rows rank after the rest
            v["corner_side"] = r.f_land is not None and r.u_now is not None and r.u_now < 0.0
            if r.phase == "idle" and r.exit in (None, "hop"):
                v["no_hit"] = frozenset({r.iid})          # its Idle: a hit makes it attack her at once, pinned
        else:
            v["hold"] = r.other
            if r.f_land is None:
                v["no_hit"] = frozenset({r.other})        # F's flag on: a hit on B is cancelled (its coin then)
                v["stance"] = self._sw_stance_x           # short of B / outside F's landing (t1)
        return v

    def _esc_observe(self, f: int, s: dict, t: float, hx: float | None, antics: list) -> None:
        cs = _sp.clappers(s)
        hp = int((s.get("hero") or {}).get("health") or 0)
        if self.esc is not None:
            self._esc_update(f, s, hx, hp, cs)
        if self.esc is None and antics and len(cs) == 2 and hx is not None and (self.asw is None
                                                                                 or self.asw.lock_end is not None):
            for e in antics:
                self._esc_start(f, s, e, cs, hx, hp)
                if self.esc is not None:
                    break
        r = self.esc
        sw_on = r is not None and r.mode == "switch" and r.f_land is None
        self._sw_stance_x = self._sw_stance(f, s) if sw_on else None
        if sw_on and self._sw_stance_x is None and clapper_by(s, r.other) is not None:
            self._esc_close(f, "b came")                 # no room short of B any more: the default play

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
        face = face_of(e)
        kind = "jump" if st == "Jump Antic" else "cast"
        why = self._esc_block(f, s, e, o, hx)
        mode = None
        if not why:
            if ESC_CORNER:
                mode = "corner"
            elif ESC_SWITCH:
                hold = c.sw_hold_j if kind == "jump" else c.sw_hold_c
                if (ox - hx) * face < hold + 0.5:
                    why = "b near"                       # no room to hold short of B (t1: F's landing hammer)
                else:
                    mode = "switch"
        self.esc = EscRun(iid=e.get("iid"), other=o.get("iid"), kind=kind, f_a=f,
                          k_a=int(round(tin * 60.0)), x0=round(cx, 3), face=face, back0=round(back, 2),
                          rel0=round((hx - cx) * face, 2), o_st=_sp.control(o)[0], o_d=round(do, 2), mode=mode,
                          hp0=hp, why=why)
        self.esc_n["runs"] += 1
        self.esc_n[f"mode_{mode}"] += 1
        if why:
            self.esc_n[f"no_switch_{why}"] += 1

    def _esc_block(self, f: int, s: dict, e: dict, o: dict, hx: float) -> str:
        """Why neither arm takes F's escape jump ("" when it can; t1): B in a jump move (its landing aims at her, the
        corner and the way to B both in reach) or casting (its outer small-rune rings reach the corner: 2 of t1's corner
        HP losses), or a rune circle (lit or to come) over the corner / her / the way to B."""
        st = _sp.control(o)[0]
        if st in JUMP_ST:
            return "other jumping"
        if st in CAST_ST:
            return "other casting"
        if st in SLAM_ST or st == "Slam Recover":
            return "other slamming"                      # (t3: its hammer hit her in F's antic twice; the playbook's)
        ox, cx = float(o["pos"][0]), float(e["pos"][0])
        wall = WALL_L if face_of(e) > 0 else WALL_R
        lo, hi = min(hx, ox, cx, wall), max(hx, ox, cx, wall)
        if any(a < hi and b > lo for a, b in self._rune_threats(f, s)):
            return "rune"
        return ""

    def _sw_stance(self, f: int, s: dict) -> float | None:
        """Arm B's stance for L2 while F's flag is on (EscCfg sw_*): short of B before F's Jump Aim, outside F's landing
        hammer / its circle after it, never nearer to B than sw_b_gap."""
        r = self.esc
        c = self.ecfg
        o = clapper_by(s, r.other)
        if o is None:
            return None
        ox = float(o["pos"][0])
        sgn = r.face                                       # from F toward the open side (B's side)
        near_b = ox - sgn * c.sw_b_gap
        if r.land_pred is None:
            x = ox - sgn * (c.sw_hold_j if r.kind == "jump" else c.sw_hold_c)
            if (x - r.x0) * sgn < c.sw_f_front:
                return None
        else:
            x = r.land_pred + sgn * (c.sw_safe_j if r.kind == "jump" else c.sw_safe_c)
            if (x - near_b) * sgn > 0:
                x = near_b
        return min(max(x, WALL_L + 0.5), WALL_R - 0.5)

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
        if hx is not None:
            r.u_now = round((hx - cx) * r.face, 2)
        if r.phase == "antic" and st in FLIGHT_ST:
            r.phase, r.f_take = "flight", f - k_st
            if hx is not None:
                # its landing is decided at the Jump Aim from her x (jump_behind.landing: 0.916 x the offset to 5 u
                # short of her, at most 12; the wall rule)
                from ssbot.combat import jump_behind as _jbm
                r.aim_hx = round(hx, 3)
                r.land_pred = round(float(_jbm.landing(r.x0, hx, r.face)), 3)
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
        if r.phase == "landed":
            return None                                    # its back slashed (the planner)
        if st != "Idle":
            r.exit = "moved"
            return None
        if r.kind == "cast":
            # behind it, no hit (esc_view), until its rune circle burst: standing still (t1: a planner dash at the wall
            # went into its turned Idle body)
            if "burst" in r.rune or f - r.f_land > c.rune_wait_f:
                r.exit = "rune"
                return None
            return self._corner_hold(f, s, ground, accepting, -u)
        k_idle = f - r.f_idle + SEND_AHEAD                 # the mask's frame from its Idle entry
        if k_idle < c.coin_f:
            return self._corner_hold(f, s, ground, accepting, -u)   # no hit on it, standing still
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

    def _corner_hold(self, f: int, s: dict, ground: bool, accepting: bool, b: float) -> int | None:
        """Arm A's wait in the corner (F idle, she behind it): no key when she stands >= hop_b_min behind it on the
        ground and B cannot reach her; else the planner."""
        if not (ground and accepting) or b < self.ecfg.hop_b_min:
            return None
        if any(x in str(((s.get("hero") or {}).get("anim") or {}).get("clip") or "") for x in NO_ATK_CLIPS):
            return None
        if other_danger(s, self.esc.iid, _sp.hero_x(s), self._rune_threats(f, s)) is not None:
            return None
        self.esc_n["corner_hold"] += 1
        return 0

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
            return self._sw_move(f, s, ground, accepting)
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

    def esc_yield(self, f: int, s: dict | None = None) -> None:
        """Another script took the keys: a running hop ends."""
        r = self.esc
        if r is not None and self._esc_hop_f is not None:
            e = clapper_by(s, r.iid) if s is not None else None
            u = None if e is None else round((_sp.hero_x(s) - float(e["pos"][0])) * r.face, 2)
            r.hop.update(j_end=f + SEND_AHEAD - self._esc_hop_f, u_end=u, end="yield")
            self._esc_close(f, "hop")

    def _sw_move(self, f: int, s: dict, ground: bool, accepting: bool) -> int | None:
        """Arm B before F's landing (t2: the planner floated on the umbrella in F's landing hammer): walk to the stance
        (_sw_stance: short of B, then past F's predicted landing), no key within 0.3 u of it; the planner while B can
        reach her."""
        r = self.esc
        x = self._sw_stance_x
        if x is None or not accepting:
            return None
        hx = _sp.hero_x(s)
        if other_danger(s, r.iid, hx, self._rune_threats(f, s)) is not None:
            return None
        self.esc_n["sw_move"] += 1
        if abs(x - hx) <= 0.3:
            return 0
        r.walk += 1
        return M_R if x > hx else M_L

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

    # ---- SP9c: the antic switch (TWO_ANTICSWITCH) ----

    def asw_skip(self) -> frozenset:
        """F while the antic switch runs: the slam playbook and the low hop leave its move alone."""
        r = self.asw
        return frozenset({r.iid}) if (ASW and r is not None and r.mode is not None and r.lock_end is None
                                      ) else frozenset()

    def asw_critical(self) -> bool:
        """The bomb hop is committed (its hold, the covering bomb's window after it): the antic switch's script keeps
        the keys ahead of the other scripts (like the low hop's critical window)."""
        r = self.asw
        if not ASW or r is None or r.mode is None:
            return False
        if r.hop_P is None:
            return r.pending                             # a covering bomb's window near: the stand / the press
        return r.k_now <= r.hop_P + max(r.hop_H, 40)

    def _asw_view(self) -> dict:
        r = self.asw
        on = r.f_off is None
        return {"iid": r.iid, "other": r.other, "mode": r.mode, "phase": r.phase, "kind": r.kind, "back0": r.back0,
                "back_u": self.acfg.back_u, "after_land": not on, "corner_aim": False, "corner_side": False,
                "hold": r.other, "no_hit": frozenset({r.other}) if on else frozenset(), "stance": r.tx}

    def _asw_observe(self, f: int, s: dict, t: float, hx: float | None, antics: list) -> None:
        cs = _sp.clappers(s)
        hp = int((s.get("hero") or {}).get("health") or 0)
        if self.asw is not None:
            self._asw_update(f, s, t, hp)
        if (self.asw is None and (self.esc is None or self.esc.mode is None) and antics and len(cs) == 2
                and hx is not None):
            for e in antics:
                self._asw_start(f, s, t, e, cs, hx, hp)
                if self.asw is not None:
                    break
        r = self.asw
        if r is not None and hx is not None:
            if r.lock_end is None:
                r.tx = self._asw_target(s, t, hx)
            thr = self._asw_threats(r, hx)
            r.pending = bool(thr) and min(w0 for w0, _, _ in thr) - r.k_now < self.acfg.bomb_lead

    def _asw_press_x(self, o: dict, sgn: int) -> float:
        """Her centre's x for the side slash on B (its body's near edge - reach_in, coming from F's side)."""
        span = body_span(o)
        near = span[0] if sgn > 0 else span[1]
        return near - sgn * self.acfg.reach_in

    def _asw_start(self, f: int, s: dict, t: float, e: dict, cs: list, hx: float, hp: int) -> None:
        c = self.acfg
        st, tin = _sp.control(e)
        kind = ASW_ANTIC[st]
        o = next(x for x in cs if x.get("iid") != e.get("iid"))
        cx, ox = float(e["pos"][0]), float(o["pos"][0])
        face = face_of(e)
        back = back_room(e)
        d, do = abs(hx - cx), abs(hx - ox)
        hy = float(((s.get("hero") or {}).get("pos") or [0.0, 0.0])[1])
        dy = hy - float(e["pos"][1])
        pr = pred_back(c, back, kind)
        self.asw_n[f"{kind}_antics"] += 1
        if d > do:
            self.asw_n["no_other_nearer"] += 1
            return
        if d > c.d_u or abs(dy) > c.dy_u:
            self.asw_n["no_far_pick"] += 1             # Close Range did not pick it
            return
        if not ((back <= c.back_u) if c.trig == 0 else (pr < c.pred_line)):
            self.asw_n["no_wall"] += 1
            return
        self.asw_n[f"{kind}_trig"] += 1
        k_now = int(round(tin * 60.0))
        ost = _sp.control(o)[0]
        sep = abs(ox - cx)
        why = ""
        if c.first and self._n_att[e.get("iid")] <= 1:
            why = "first"
        elif (ox - cx) * face <= 0:
            why = "b behind"
        elif ost not in ("Idle", "Walk"):
            why = "b busy"
        elif sep < (c.sep_slam if kind == "slam" else c.sep_min):
            why = "sep"
        elif any(a < max(hx, ox) and b > min(hx, ox) for a, b in self._rune_threats(f, s)):
            why = "rune"
        else:
            # she reaches the press point by F's tail end (and a slam: out of its hammer by hammer_k): the run with one
            # dash held into the ground sprint (cast_stab.sprint_travel: ~7.3 u by the release at Sprint Grace)
            jmax = _cs.DASH_F + c.grace_f + 1

            def frames(dist: float) -> float:
                if dist < c.dash_min:
                    return max(0.0, dist) / WALK_U
                for j in range(1, jmax + 1):
                    if _cs.sprint_travel(j) >= dist:
                        return float(j)
                return jmax + (dist - _cs.sprint_travel(jmax)) / WALK_U
            k_off = c.k_off_slam if kind == "slam" else c.k_off_cast
            # (the spec: she can be within 8.3 u of B by F's flag-off) the hold point by the step-in + slack
            if k_now + SEND_AHEAD + frames((ox - face * c.hold_b - hx) * face) > k_off - c.step_spare + c.far_slack:
                why = "far"
            elif kind == "slam" and k_now + SEND_AHEAD + frames((cx + face * c.hammer_u - hx) * face) > c.hammer_k:
                why = "hammer"
        run = AswRun(iid=e.get("iid"), other=o.get("iid"), kind=kind, f_a=f, k_a=k_now, ta=t - tin, x0=round(cx, 3),
                     face=face, back0=round(back, 2), pred=round(pr, 2), sep0=round(sep, 2),
                     rel0=round((hx - cx) * face, 2), o_st=ost, o_d=round(do, 2), mode=None if why else "aswitch",
                     hp0=hp, why=why, o_prev=ost)
        if why:
            self.asw_n[f"no_{why}"] += 1
            run.end, run.f_end = "not taken", 0
            self.asw_done.append(run)
            return
        self.asw = run
        self._asw_dash = None
        self.asw_n["runs"] += 1
        self.asw_n[f"runs_{kind}"] += 1

    def _asw_update(self, f: int, s: dict, t: float, hp: int) -> None:
        r = self.asw
        c = self.acfg
        for ev in s.get("ev") or ():
            d = ev.get("d") or {}
            if ev.get("k") == "hit" and d.get("type_key") == CLAPPER and (d.get("dealt") is None
                                                                            or float(d.get("dealt")) > 0):
                tgt = d.get("ent") or d.get("iid")
                if tgt == r.iid:
                    r.hits_f.append((f - r.f_a, r.phase))
                elif tgt == r.other:
                    r.hits_b.append((f - r.f_a, r.phase))
                    if r.f_off is not None and r.hit_b is None:
                        r.hit_b = f - r.f_off
        if hp < r.hp0:
            r.hp.append(f - r.f_a)
        r.hp0 = hp
        k = int(round((t - r.ta) * 60.0))
        r.k_now = k + SEND_AHEAD
        self._asw_bombs(r, s, k)
        if r.lock_end is not None:
            # the bomb phase: until F's rings have passed her (and a hop has landed)
            if k - (r.k_off or k) > c.bomb_f and r.hop_P is None:
                self._asw_close(f, r.lock_end, final=True)
            return
        e = clapper_by(s, r.iid)
        o = clapper_by(s, r.other)
        if o is None:
            self._asw_close(f, "B dead")
            return
        ost = _sp.control(o)[0]
        if r.other in self.entry:
            r.b_idle.append(f - r.f_a)
        if ost == "Evade Scuttle" and r.b_evade is None:
            r.b_evade = f - r.f_a
        st = _sp.control(e)[0] if e is not None else None
        if r.f_off is None and (e is None or st not in ASW_ON_ST[r.kind]):
            r.f_off, r.k_off, r.phase = f, k, "tail"           # its flag is off (or it died)
        if r.kind == "slam" and r.f_rec is None and (e is None or st not in ASW_HAMMER_ST + ("Slam Antic",)):
            r.f_rec = f                                          # its hammer is gone
        if r.f_off is not None and r.f_idle is None and (e is None or st not in ("Slam 2", "Slam Effects?",
                                                                                 "Slam Recover", "Cast 2")):
            r.f_idle, r.phase = f, "after"
        o_new = ost != r.o_prev or r.other in self.entry
        r.o_prev = ost
        if r.f_off is not None and ost in MOVE_ST and o_new and f > r.f_off:
            r.b_next, r.k_next = ost, f - r.f_off
            self._asw_close(f, "B move")
        elif r.hit_b is not None:
            self._asw_close(f, "hit")
        elif r.f_off is not None and f - r.f_off > c.end_f:
            self._asw_close(f, "end")
        elif r.f_off is None and k > (c.k_off_slam if r.kind == "slam" else c.k_off_cast) + 40:
            self._asw_close(f, "late")

    def _asw_close(self, f: int, why: str, final: bool = False) -> None:
        r = self.asw
        if r is not None and not final and r.kind == "cast" and r.f_off is not None and r.lock_end is None:
            # the lock-in ends; F's small-rune rings still to pass her: the bomb phase (the hop) keeps the run
            r.lock_end, r.f_lock, r.phase = why, f - r.f_a, "bomb"
            self.asw_n[f"lock_{why}"] += 1
            self._asw_dash = None
            return
        if r is not None:
            if r.lock_end is None:
                r.lock_end, r.f_lock = why, f - r.f_a
            r.f_end, r.end = f - r.f_a, r.lock_end
            self.asw_done.append(r)
            self.asw_n[f"end_{r.end}"] += 1
        self.asw = None
        self._asw_dash = None

    def _asw_bombs(self, r: AswRun, s: dict, k: int) -> None:
        """The small-rune bombs' appearance / light per object (rune_lowhop's bookkeeping): the unlit ones there before
        F's flag-off are stale (t1: the pool keeps an earlier cast's unlit row in place) until one lights or is placed
        anew."""
        from ssbot.combat import rune_bombs as _rb
        cur = {}
        for iid, bx, by, lit in _rb.bomb_ents(s.get("ents")):
            cur[iid] = lit
            b = r.bombs.get(iid)
            if b is not None and abs(b["x"] - bx) > 0.3:
                b = None                                   # a pooled object placed anew
            if b is None:
                b = r.bombs[iid] = {"x": round(bx, 3), "y": round(by, 3), "a": k, "on": None, "end": False,
                                    "stale": r.f_off is None and not lit}
            if lit:
                b["stale"] = False
                if b["on"] is None:
                    b["on"] = k
            elif b["on"] is not None:
                b["end"] = True
        for iid, b in r.bombs.items():
            if iid not in cur and (b["on"] is not None or k > b["a"] + 21 + 7 + 2):
                b["end"] = True

    def _asw_threats(self, r: AswRun, hx: float) -> list[tuple[int, int, float]]:
        """[(w0, w1, thr)]: the live bombs covering her x - antic frames her box bottom must stay above thr."""
        from ssbot.combat import rune_lowhop as _rl
        c = self.acfg
        out = []
        for b in r.bombs.values():
            if b["end"] or b["stale"]:
                continue
            dx = abs(hx - b["x"])
            if dx >= _rl.R + HALF_W + c.x_pad:
                continue
            w0, w1 = (b["on"], b["on"] + 6) if b["on"] is not None else (b["a"] + 20, b["a"] + 21 + 6)
            out.append((w0 - 1, w1 + 1, _rl.bomb_top(b["y"], max(0.0, dx - c.x_pad)) + c.margin))
        return out

    def _asw_target(self, s: dict, t: float, hx: float) -> float | None:
        """The run's target x (module docstring): the hold point short of B, the press point from the step-in (F's
        lock) or at once (its tail); a slam: never inside the hammer line until its Slam Recover; never nearer to B than
        gap_b."""
        r = self.asw
        c = self.acfg
        o = clapper_by(s, r.other)
        if o is None:
            return None
        sgn = r.face
        ox = float(o["pos"][0])
        press = self._asw_press_x(o, sgn)
        k = int(round((t - r.ta) * 60.0)) + SEND_AHEAD
        if r.f_off is None:
            # (t1, 931052a: entering B's Slam Range during F's lock let an idle B's evade coin fire at once, 2 of 3
            # runs - B slid away and jumped) the hold point outside its Slam Range until step_spare frames before F's
            # predicted flag-off: she enters its range about when F's flag goes off (B then decides: a walking B on
            # its range check, an idle one on her hit or its coin's evade, chased)
            k_off = c.k_off_slam if r.kind == "slam" else c.k_off_cast
            pd = (ox - press) * sgn                              # the press point's distance from B's centre
            db = (ox - hx) * sgn
            if k >= k_off - c.step_spare:
                tx = press
            elif db > c.hold_b:
                tx = ox - sgn * c.hold_b
            else:
                tx = hx if db >= pd else press                   # inside the hold point: stay (not back to F)
        else:
            tx = press
        if r.kind == "slam" and r.f_rec is None:
            line = r.x0 + sgn * c.hammer_u
            if (tx - line) * sgn < 0:
                tx = line
        if (ox - tx) * sgn < c.gap_b:
            tx = ox - sgn * c.gap_b
        return min(max(tx, WALL_L + 0.5), WALL_R - 0.5)

    def _asw_step(self, f: int, s: dict, ground: bool, accepting: bool, t: float, latch) -> int | None:
        """The antic switch's keys (module docstring): the walk / dash to the target, the re-hit on B's Idle (re-)entry
        in F's lock, the deciding side slash on B from F's flag-off."""
        r = self.asw
        c = self.acfg
        if r.mode is None:
            return None
        sec = self._second(f)
        if sec is not None:
            return sec
        h = s.get("hero") or {}
        tm = h.get("tm") or {}
        clip = str((h.get("anim") or {}).get("clip") or "")
        k = int(round((t - r.ta) * 60.0)) + SEND_AHEAD          # the mask's antic frame
        hx = _sp.hero_x(s)
        dm = self._asw_dash
        if dm is not None:
            # the dash held into the ground sprint, released inside Sprint Grace (closed loop on her x and speed: cast_stab
            # T2), then no key until she has control again
            j = f + SEND_AHEAD - dm["f0"]
            sg = 1 if dm["dir"] == M_R else -1
            if dm.get("rel") is None:
                v = abs(float((h.get("vel") or [0.0, 0.0])[0]))
                remain = ((r.tx if r.tx is not None else hx) - hx) * sg
                if j > _cs.DASH_F and (remain - c.release_lag * v / 60.0 <= 0.3 or j > _cs.DASH_F + c.grace_f):
                    dm["rel"] = j
                    return 0
                return dm["dir"] | M_DASH
            if ground and accepting and clip != "Dash" and not clip.startswith(_cs.STOP_WAIT_CLIPS):
                dm["ctl"] = j
                r.dash_end = f
                self._asw_dash = None
            elif j > dm["rel"] + 40:
                self._asw_dash = None
            else:
                return 0
        # the bomb hop (a cast's small runes at her x: "cast only with the bomb hop", switch answer 2f / section 3)
        if r.hop_P is not None:
            j = k - r.hop_P
            if (ground and j > 4) or j > 50:
                r.hop_P = None                                   # landed
            else:
                return M_J if j < r.hop_H else 0
        thr = self._asw_threats(r, hx)
        if thr and min(w0 for w0, _, _ in thr) - k < c.bomb_lead:
            if not ground or not accepting:
                return None                                      # (the planner's bomb forecast)
            from ssbot.combat import rune_lowhop as _rl
            plan = _rl.hop_plan(thr, k, range(9, 17), 3)
            if plan is None:
                self.asw_n["hop_none"] += 1
                return None
            if plan["P"] <= k and (latch is None or bool(int(latch(M_J)) & M_J)):
                r.hop_P, r.hop_H = k, plan["H"]
                r.hops.append((k, plan["H"], min(w0 for w0, _, _ in thr), max(w1 for _, w1, _ in thr)))
                self.asw_n["hops"] += 1
                return M_J
            return 0                                             # stand still over the planned x until the press
        if r.lock_end is not None:
            return None                                          # the bomb phase: nothing else
        if not accepting or r.tx is None:
            return None
        o = clapper_by(s, r.other)
        if o is None:
            return None
        hxw = self._xw(s)
        ox = float(o["pos"][0])
        ost = _sp.control(o)[0]
        look = 1 if ox > hxw else -1
        toward_b = M_R if look > 0 else M_L
        span = body_span(o)
        u0 = (hxw - r.x0) * r.face
        in_hammer = r.kind == "slam" and r.f_rec is None and -1.91 - HALF_W < u0 < c.hammer_u
        # the presses (not in the dash combo's window after a sprint: an attack then is the Wanderer dash combo)
        want = False
        if r.f_off is None:
            # F's lock: the re-hit on B's Idle (re-)entry before its coin
            if ost == "Idle" and r.b_idle and (f - r.f_a) - r.b_idle[-1] <= c.lock_win and not (
                    r.presses and r.presses[-1][0] >= r.b_idle[-1]):
                want = "lock"
        elif r.hit_b is None and ost in ("Idle", "Walk") and not (in_hammer and k >= c.hammer_k - 6):
            want = "decide"
        combo = r.dash_end is not None and f - r.dash_end < c.combo_f
        if want and ground and not combo and slash_meets(hxw, look, span) and self._atk_ready(s):
            if not self._facing(s, look):
                return toward_b
            r.presses.append((f - r.f_a, want, round(abs(hxw - ox), 2)))
            self.asw_n[f"press_{want}"] += 1
            return self._press(f, toward_b)
        # the walk (the dash-sprint when the run alone is late)
        tx = r.tx
        dist = abs(tx - hx)
        if r.kind == "slam" and r.k_line is None and (hx - (r.x0 + r.face * c.hammer_u)) * r.face >= 0:
            r.k_line = k
        if dist <= 0.3:
            if r.k_hold is None:
                r.k_hold = k
            return 0
        toward = M_R if tx > hx else M_L
        if r.f_off is None and (ox - tx) * r.face >= c.hold_b - 0.05 or (r.kind == "slam" and r.k_line is None):
            # the dash (held into the sprint) only to reach the hold point by the step-in / the hammer line by
            # hammer_k (the step-in walks: she keeps the dash for the chase of B's evade, no dash combo window)
            k_off = c.k_off_slam if r.kind == "slam" else c.k_off_cast
            deadline = c.hammer_k if (r.kind == "slam" and r.k_line is None) else k_off - c.step_spare
        else:
            deadline = k + 999
        late = k + dist / WALK_U > deadline
        if (late and ground and dist >= c.dash_min and float(tm.get("dash_cd") or 0.0) <= 0.02
                and float(tm.get("atk_cd") or 0.0) <= 0.19 and not any(x in clip for x in NO_ATK_CLIPS)
                and self._asw_prev & toward and _cs._clean(latch, toward | M_DASH)):
            self._asw_dash = {"f0": f + SEND_AHEAD, "dir": toward, "rel": None}
            r.dash.append(k)
            self.asw_n["dash"] += 1
            return toward | M_DASH
        r.walk += 1
        return toward

    def asw_stats(self) -> dict:
        runs = self.asw_done + ([self.asw] if self.asw is not None else [])
        out = dict(self.asw_n)
        out["asw_runs"] = [{"f_a": r.f_a, "kind": r.kind, "mode": r.mode, "why": r.why, "k_a": r.k_a,
                            "back0": r.back0, "pred": r.pred, "sep0": r.sep0, "rel0": r.rel0, "o_st": r.o_st,
                            "o_d": r.o_d, "off": None if r.f_off is None else r.f_off - r.f_a, "k_off": r.k_off,
                            "rec": None if r.f_rec is None else r.f_rec - r.f_a,
                            "idle": None if r.f_idle is None else r.f_idle - r.f_a, "hits_f": r.hits_f,
                            "hits_b": r.hits_b, "b_idle": r.b_idle, "b_evade": r.b_evade, "hp": r.hp,
                            "presses": r.presses, "dash": r.dash, "k_line": r.k_line, "k_hold": r.k_hold,
                            "hit_b": r.hit_b, "hit_in_tail": r.hit_b is not None and 0 <= r.hit_b <= (
                                self.acfg.tail_slam if r.kind == "slam" else self.acfg.tail_cast) + 2,
                            "lock_hits": [x for x in r.hits_b if x[1] == "go"],
                            "b_next": r.b_next, "k_next": r.k_next, "walk": r.walk, "f_end": r.f_end,
                            "end": r.end, "lag": r.k_a, "f_lock": r.f_lock, "hops": r.hops,
                            "bombs_live": sum(1 for b in r.bombs.values() if not b["stale"])} for r in runs]
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
            corner_own = ESC and self.esc is not None and self.esc.mode == "corner" and self.esc.iid == e.get("iid")
            if j is not None and not j.get("done") and j["aim_hx"] is not None and not corner_own:
                # (SP9b arm A: the corner owns the focus's own escape jump - behind its landing)
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
        if ASW:
            res["asw"] = self.asw_stats()
        return res


def intro_keys(s: dict) -> int:
    """SSBOT_FORUM_TWO_OPEN: the harness's key mask in the wave-start intro (the load -> the wave's activation): left
    while her x is right of OPEN_INTRO_X, else none."""
    h = s.get("hero") or {}
    if not (h.get("box") or h.get("pos")) or not h.get("hero_accepting_input", True):
        return 0
    return M_L if _sp.hero_x(s) > OPEN_INTRO_X else 0

