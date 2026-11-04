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
from ssbot.combat import rune_pogo as _rp
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
# SP9c (the lead's note of 2026-10-17, item 2b - the person: "if it is already too close and the only choice is taking a
# hit or the corner, of course choose the corner"): with the switch on, the corner (arm A) takes F's escape jump when the
# switch's only failed gate is "b near" (B too close to hold short of it); default off (=1 on; arm sp9bAB)
ESC_FALLBACK = ESC_SWITCH and _on("SSBOT_FORUM_TWO_ESC_FALLBACK")
# SP11a (task 1v1 SP11a; the person's big-rune sequence, the lead's NOTE 4 / 5 of 2026-10-17; combat.rune_pogo):
# default off (=1 on). F's escape jump CAST with B free: L2 holds B, she goes to B's face and slashes it through F's
# lock, then the altitude controller (a pogo on B's head, the umbrella; the hero model's plans against F's landing
# hammer, its circle's dome, B's body / hammer) to the circle's burst; "far" (her spot at B clear of both at F's aim)
# hands back at once. Plain escape jumps keep TWO_WALLSWITCH; with TWO_ESC_FALLBACK the corner takes the casts the tier
# does not (B busy, she behind F, B too near F).
# SP12b (task 1v1 SP12b; SP11a's failures, the lead's NOTES 8 / 9 and 05:06 note; combat.rune_pogo RtCfg v2): default off
# (=1 on; it turns RUNETIER on with v2). Every jump cast of either Clapper: the pass under the caster to behind its landing
# first (the escape casts too: from B's face or the lure point p_need + lure_m), the pogo on B the fallback; the small-rune
# bombs in every plan; a pogo run ends when B leaves / slams with the circle not due; behind the landing the run ends and
# L2 holds the caster (its rune hold) to the burst + 0.5 s; far casts in the Clawline band optionally to claw_chase.
RT2 = _on("SSBOT_FORUM_TWO_RT2")
RUNETIER = _on("SSBOT_FORUM_TWO_RUNETIER") or RT2
# SSBOT_FORUM_TWO_FLIPB (task 1v1 SP14, default off; the person 2026-10-18 ~09:40 / 14:35 / 14:40, TWO_CLAPPER_OPEN_ITEMS
# B: "she is between the two, the wall-side one jump-casts ... flipping over the OTHER Clapper would be better"; variant
# (c): a small hop + the Clawline at B + a down slash on B, B locked until the caster lands): F's escape jump cast
# (TWO_WALLSWITCH's run: F's back <= 6.2 u from its wall, she within 8.3 u and nearer F than B) with B on her far side
# (B not jumping / casting / slamming: F's antic locks it, a hit is cancelled), B's front edge 0.5 - 9 u ahead of her
# (the ray's 10.5 u less the antic's drift), she on the ground with silk and the harpoon, no small-rune bomb on her way,
# and (trig nat) the circle's far edge from her x now (landing + 13.67 u) not short of B's front - 0.5 u (no standing
# room outside it short of B) and room past B for the spot outside the circle's far edge as predicted from her x at the
# press (her x then ~ B's front - 2 u: F's aim falls in the hook): mode "flipb" instead of "switch". The run: the jump
# held hop_hold frames, the turn key, the Clawline toward B at press_k (2 frames), no key until control (the hook's
# contact off to control + 0.2 s), then the key away from F (drift past B) with a down slash on B's head when its body is
# below her in reach (<= ds_max, the pogo's i-frames), until she lands; then L2 holds B with the stance just outside
# the circle's far edge (out_m past it, past B's back when B stands there), hits on B allowed from F's landing on (its
# slam: the playbook), until the circle's burst + 30 frames. SSBOT_FORUM_TWO_FLIPB_SET "trig=force,press_k=12".
FLIPB = _on("SSBOT_FORUM_TWO_FLIPB")
FB = {"trig": "nat", "hop_hold": 10.0, "press_k": 12.0, "ds_max": 2.0, "ds_reach": 1.4, "ds_top": 2.6, "out_m": 0.6,
      "gap_max": 9.0, "end_f": 30.0, "k_late": 35.0, "air_yb": 3.0}
# fpfb1 (a94e6b2, w13 fb / fbf, 24 episodes): no run - 8 escape jump casts reached the gate, 4 with her in the air at
# F's antic, 4 with B finishing a move -> the gate is re-checked every tick of F's antic to k_late (35: control by ~k 80,
# B locked to 97); in the air (no hop) the press when her throw's band meets B's standing body (her box bottom at the
# throw <= air_yb above the floor, vy -6 .. +9 u/s: CLAWSTRIKE's fit); B in Slam Recover / After Scuttle counts as free
FB_OK_B = ("Slam Recover", "After Scuttle")
for _kv in os.environ.get("SSBOT_FORUM_TWO_FLIPB_SET", "").replace(";", ",").split(","):
    if "=" in _kv:
        _k, _v = (_x.strip() for _x in _kv.split("=", 1))
        if _k not in FB:
            raise KeyError(f"SSBOT_FORUM_TWO_FLIPB_SET: unknown key {_k!r}")
        FB[_k] = _v if _k == "trig" else float(_v)
M_CLAW = 1 << 4             # the clawline button (ssbot.ipc.framing.BUTTONS order; key S)
ESC = ESC_CORNER or ESC_SWITCH or RUNETIER or FLIPB
# SP9c (forum.md 78): the close-only antic switch, an A/B arm (default off, =1 on)
ANTICSWITCH = _on("SSBOT_FORUM_TWO_ANTICSWITCH")
# SP11b (task 1v1 SP11b; bigrune/answer.txt section 1 and 4, the person: "switch target early enough to reduce the
# corner big runes"): default off (=1 on). The antic switch's run (AswRun) with the spec's numbers - slams only (casts=0),
# trigger T8.1 (F's back <= 8.1 u), also on F's first attack (first=0), F-B >= 17.1 u (sep_slam: F lunges 3.6 u, so her
# press point at B stays >= 8.55 u from F) and her predicted centre >= 8.55 u from F's lunged centre at F's Idle + 15
# (AswCfg.early: antic + k_i15) - else no switch. SSBOT_FORUM_TWO_EARLY_SET overrides those AswCfg numbers. With
# TWO_ANTICSWITCH also on, the antic switch's own numbers (SSBOT_FORUM_TWO_ASW_SET) win.
EARLY = _on("SSBOT_FORUM_TWO_EARLYSWITCH")
ASW = ANTICSWITCH or EARLY
# SP10c (the lead's NOTE 4 / 5 of 2026-10-17, the person: "the moment one starts its jump antic she can already go and
# hit the other one" - part of the target-switch controller; forum.md 81): default off (=1 on)
JUMPHIT = _on("SSBOT_FORUM_TWO_JUMPHIT")
# SP11-0 (task 1v1 SP11-0, the SP10 cause audits: one-Clapper scripts acting while the other Clapper hit her - the chase 10
# of 68 HP losses in SP10c's T2, the low hop's stance in the other's big rune, the slam playbook's way out drifting into
# the other's landing): default off (=1 on). TwoPlay.guard_spans gives the other Clapper's danger spans (its jump landing
# band once its Jump Aim fixed it, its big rune circle lit or to come, its hammer in a slam, its body) and the chase (no
# start / abort with her inside one, never a key / dash that takes her into one on the way to the focus), the low hop (no
# start / abort with its stance or her x in one) and the slam playbook (the way out's side away from them) use them.
# SP11-0 A/B (9789b37, 2 x 32 per arm, block design, the same seeds 5200000.. / 5300000..; the person's rule: the arm
# best on HP-hitless clears and not worse on the others): s11g (TWO_GUARD + TWO_COMMIT + TWO_RUNEGATE) vs rnjb -
# hitless clears 12 vs 8 / 64 (+0.063, 90 % -0.047 .. +0.172), both killed 48 vs 35 (+4 .. +22), landed / s 1.335 vs
# 1.305 (-0.025 .. +0.083), HP hits / min 3.11 vs 4.64 (-2.38 .. -0.67); s11gr (without TWO_COMMIT) 7 / 35 / 1.306 /
# 4.47. Since then TWO_GUARD follows SSBOT_FORUM_V2 when unset (=0 off; arm rnsp11_0 = the SP10c default); the low
# hop's part stays off (GuardCfg.low)
GUARD = _on("SSBOT_FORUM_TWO_GUARD", _V2)
# SP11b (task 1v1 SP11b; bigrune/answer.txt section 1 - how the focus ends at its wall: its own Idle-coin evade 43 %, the
# opening 22 %, an evade after her hit 13 %, her knock-back 8 % - and the lead's NOTE 6): each default off (=1 on)
#   TWO_WALKOUT  (WoCfg) the coin needs her within 8.3 u of F at its Idle (beyond it F walked out 85 %): F (L2's target)
#                with its back within back_u of its wall and B not attacking -> she stands d_u from F on its open side
#                through F's Idle entries (no hit on F) while F walks out toward her, until F's back >= draw_u, F starts
#                a move, B moves or the time is up; with open=1 also the opening (she waits at c2 + d_u, no slash)
#   TWO_OPENPUSH (OpCfg) the opening (the wake .. c2's first move): no hit on c2 while its back < back_u (each front
#                slash pushes it 0.48 u; it lands 0.8 u outside its escape line) - the opening script's and IdleHit's
#                presses and the planner's hits on c2 (GoalPrefs.no_hit)
#   TWO_RUNLOCK  (combat.tactics.gauntlet) the switch rule's "focus committed" run bounded by the focus's LOCK end
#                (slam 0.92 s, cast 0.81, jump 1.21, jump cast 1.63 s from its antic), not its move's end; after such a
#                switch no hit on the new target while the old one's flag is on (the deciding hit in its tail)
#   TWO_PUSHMID  (PmCfg) at F's close Slam Antic with F's outer room smaller than B's and the run to B failing the
#                lock-bounded check: the slam playbook's way out to F's wall side (over its body), then L2 holds F
#                with the stance on its wall side (her slashes herd it toward the middle) - ret 1: for one F move
#                (until its next antic), ret 2: until the lock-bounded run check to B passes
WALKOUT = _on("SSBOT_FORUM_TWO_WALKOUT")
OPENPUSH = _on("SSBOT_FORUM_TWO_OPENPUSH")
RUNLOCK = _on("SSBOT_FORUM_TWO_RUNLOCK")
PUSHMID = _on("SSBOT_FORUM_TWO_PUSHMID")
# SP13b (the person, 2026-10-18: "stand on the ground, slash twice, and when the small runes are about to come out flip
# over"): SSBOT_FORUM_TWO_PMCAST, default off (=1 on; SSBOT_FORUM_TWO_PMCAST_SET: combat.push_cast.PcCfg) - TWO_PUSHMID's
# CAST route: at F's close Spell Antic (trig nat: she nearer F than B and within d_max in front of it, F's outer room +
# hyst < B's, B idle / walking, the lock-bounded run to B failing; trig force: any close cast of F, either encounter -
# the fixed point) with room_c behind F, the low hop's run on F (its ground slashes) plays the over plan
# (combat.push_cast: the jump, the down slash on F's head, the bounce to F's wall side, landing behind ring 1) instead of
# its hop; landed on F's wall side the herd (L2 holds F, the stance 3.5 u on its wall side), ret 1 / ret 2 as PUSHMID's
PMCAST = _on("SSBOT_FORUM_TWO_PMCAST")
PMANY = PUSHMID or PMCAST
SP11B = WALKOUT or OPENPUSH or RUNLOCK or PMANY
# SP12a (task 1v1 SP12a; the SP11 cause audits' top cause - the planner in the air with the dash ready and no safe row,
# FORCED_RISK streaks of 15-53 frames before 44 of 45 such HP losses of SP11b's default): default off (=1 on).
#   TWO_RUNEEXIT (ReCfg) the open-loop replays of those streaks (sp12\fr1): even with no margin no row was free - she was
#                already trapped; 19 of the 45 were a jump cast's big rune circle (centre 6.48 / 6.75 u in front of the
#                landing, r 7.19, lit landing + 62 .. 88) with her inside it and the way out too long (8+ u), past the
#                wall or through a Clapper's body. The circle is known from the caster's Jump Aim (~117 frames before
#                it lights), the planner sees 36 + 24 frames: it kept hitting inside the circle until no exit was left.
#                On: every tick TwoPlay.rune_exit gives the planner each jump cast's circle still to light (past its aim
#                or landed, not burst) and the Clappers' bodies (grounded now; a jumper's at its landing from its
#                landing - 10 frames); the planner ranks the safe rows whose end is inside a circle with no exit left
#                in time (an edge inside the walls, no body on the way, reached at the run's speed + a buffer before
#                the circle lights) after the safe rows that keep one, above the landed hits and NODASH
#                (GoalPrefs.rune_exit; forum_planner "rune exit").
RUNEEXIT = _on("SSBOT_FORUM_TWO_RUNEEXIT")
# SP12b (the lead's NOTE 3 of 2026-10-18, the person: "behind the big rune it is the SAME Clapper - two more hits are
# always good"): default off (=1 on; acts only with TWO_RT2). Through RT2's rune hold behind the caster's landing the
# hits on the caster count (from the ground: gauntlet's "rune: behind" ground_hit) and IdleHit may slash it while her
# x stays >= hold_hit_u behind the landing (the circle starts 0.71 u behind it + her half width + a margin); the chase
# of its evade stays off (its evade slides into its own circle).
HOLDHIT = _on("SSBOT_FORUM_TWO_HOLDHIT")
HOLD_HIT_U = 1.5
ANY = IDLEHIT or SPACE or OPEN or ESC or ASW or JUMPHIT or GUARD or SP11B or RUNEEXIT   # the policy's TwoPlay object

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


@dataclass
class GuardCfg:
    """SSBOT_FORUM_TWO_GUARD (SP11-0): the other Clapper's danger spans (u, centre to centre, her box centre's x)."""
    land_back: float = 3.0      # a jump's landing band behind the landing (its falling Air body: SP10c fp1, 1.8-1.95 u
    #                             behind was hit 16 / 19, 3.0 u safe)
    land_front: float = 8.3     # ... in front (Slam Collider 2 0.67-7.76 u + her half width 0.25 + 0.3)
    land_tail_f: int = 12       # ... until this many frames after its landing (Slam 2's collider), then its body
    rune_c: float = 6.48        # the big rune circle's centre in front of the landing ...
    rune_r: float = 7.74        # ... and its reach (r 7.19 + her half width 0.25 + 0.3)
    hammer_u: float = 12.5      # a slam's hammer in front of its centre (slam_play.TWO_SLAM_U)
    hammer_back: float = 1.9    # ... behind it (its back 1.34 + 0.25 + 0.3)
    body_pad: float = 0.55      # around a body (her half width + 0.3)
    low: int = 0                # 1: the low hop takes the spans too (fixed points: 3251a4a 5 of 9 guard no-starts / aborts
    #                             without HP lost, 4cb5880 - its big rune circle only - 0 of 1: off, its own trial switch)


@dataclass
class ReCfg:
    """SSBOT_FORUM_TWO_RUNEEXIT (SP12a): a jump cast's big rune circle for the planner's exit tier (u, centre to centre;
    frames of 1/60 s)."""
    c_left: float = 6.48        # the circle's centre in front of the landing, facing left / right (bigrune answer.txt)
    c_right: float = 6.75
    reach: float = 7.72         # r 7.19 (the dome at her box bottom) + her half width 0.23 + 0.3
    land_f: float = 110.0       # a jump cast's landing after its antic entry (flight from +54 .. 56)
    lit_f: float = 62.0         # the circle lights from landing + 65 (p5) - 3 ...
    end_f: float = 88.0         # ... to landing + 85 + 3 (RG_LIT, slam_play)
    horizon_f: float = 180.0    # circles lighting later than this are not passed
    body_pad: float = 0.55      # around a body (her half width + 0.3)
    jump_body: float = 2.5      # a jumper's body around its landing
    jump_block_f: float = 10.0  # ... from its landing - this
    v: float = 8.25 / 60.0      # her run (u / frame)
    buf_f: float = 8.0          # frames of slack before the circle lights
    wall_pad: float = 0.3       # an edge this close to a wall does not fit


def _re_cfg() -> ReCfg:
    """SSBOT_FORUM_TWO_RUNEEXIT_SET="buf_f=12": trial overrides of the ReCfg numbers."""
    return _set_cfg(ReCfg(), "SSBOT_FORUM_TWO_RUNEEXIT_SET")


def rune_exit_late(cxe, rx, k_end: float, walls=(None, None)):
    """SSBOT_FORUM_TWO_RUNEEXIT: [len(cxe)] True where a row ending at x cxe (frame k_end from the planner's origin) is
    inside a circle of rx = (circles, bodies, cfg numbers) that lights after k_end with no way out left in time: each
    side's edge (centre +- reach) inside the walls, no body span [lo, hi] blocking from k_from on between cxe and the
    edge when she gets there, reached at v u / frame + buf_f frames before the circle's first lit frame."""
    import numpy as np
    cxe = np.asarray(cxe, np.float64)
    late = np.zeros(cxe.shape, bool)
    if not rx:
        return late
    circles, bodies, num = rx
    v, buf, pad = num["v"], num["buf_f"], num["wall_pad"]
    wl = (WALL_L if walls[0] is None else walls[0]) + pad
    wr = (WALL_R if walls[1] is None else walls[1]) - pad
    for cx, reach, k_on, _k_off in circles:
        if k_on <= k_end:
            continue                                   # lit within the row: the planner's own check has it
        inside = np.abs(cxe - cx) < reach
        if not inside.any():
            continue
        lead = k_on - k_end - buf
        ok = np.zeros(cxe.shape, bool)
        for d in (-1.0, 1.0):
            edge = cx + d * reach
            if not wl <= edge <= wr:
                continue
            dist = np.abs(edge - cxe)
            side_ok = dist / v <= lead
            for lo, hi, k_from in bodies:
                # a body between her end and the edge, reached when it already blocks
                near = np.where(d > 0, lo, hi)
                between = ((d > 0) & (hi > cxe) & (lo < edge)) | ((d < 0) & (lo < cxe) & (hi > edge))
                t_at = k_end + np.maximum((near - cxe) * d, 0.0) / v
                side_ok &= ~(between & (t_at >= k_from))
            ok |= side_ok
        late |= inside & ~ok
    return late


def _guard_cfg() -> GuardCfg:
    """SSBOT_FORUM_TWO_GUARD_SET="land_back=3.3": trial overrides of the GuardCfg numbers."""
    return _set_cfg(GuardCfg(), "SSBOT_FORUM_TWO_GUARD_SET")


GUARD_ALL = ("land", "rune", "hammer", "body")


def guard_hit(spans, lo: float, hi: float, kinds=GUARD_ALL, own=None) -> str | None:
    """SSBOT_FORUM_TWO_GUARD: the kind of the first span (of another Clapper than own, or a circle) that meets
    [lo, hi], or None."""
    for a, b, kind, iid in spans or ():
        if kind in kinds and (iid is None or iid != own) and a < hi and b > lo:
            return kind
    return None


def guard_room(spans, x: float, d: int, kinds=GUARD_ALL, own=None) -> float:
    """SSBOT_FORUM_TWO_GUARD: how far (u) she can move from x in world direction d before a span's near edge (99 with
    none that way; 0 when x is inside one)."""
    room = 99.0
    for a, b, kind, iid in spans or ():
        if kind not in kinds or (iid is not None and iid == own):
            continue
        if a < x < b:
            return 0.0
        edge = a - x if d > 0 else x - b
        if edge >= 0.0:
            room = min(room, edge)
    return room


def guard_exit(spans, x: float, d: int, kinds=GUARD_ALL, own=None) -> tuple[float, float, str | None]:
    """SSBOT_FORUM_TWO_GUARD (fp1 fix): with x inside spans, (the distance (u) out of them in world direction d, the room
    past that exit to the next span, the kind she is in); (0, guard_room, None) when x is in none."""
    use = [(a, b, kind) for a, b, kind, iid in spans or () if kind in kinds and not (iid is not None and iid == own)]
    e, kind0 = x, None
    for _ in range(len(use) + 1):
        inside = [(a, b, kind) for a, b, kind in use if a < e < b]
        if not inside:
            break
        kind0 = kind0 or inside[0][2]
        e = max(b for _, b, _ in inside) + 0.01 if d > 0 else min(a for a, _, _ in inside) - 0.01
    return abs(e - x), guard_room(spans, e, d, kinds, own), kind0


# ---- SP11b: the focus at its wall ----
MOVE_KIND = {"Slam Antic": "slam", "Spell Antic": "cast", "Jump Antic": "jump", "Cast Slam Antic": "jc"}
# the buddy lock (its flag on): the antic start to Slam 2 / Cast 2 (buddy/answer.txt; lower bounds in frames)
LOCK_F = {"slam": 55, "cast": 48, "jump": 72, "jc": 97}
LOCK_ST = {"slam": ("Slam Antic", "Slam 0", "Slam 1", "Slam Effects?"), "cast": ("Spell Antic", "Cast 1"),
           "jump": ("Jump Antic", "Jump Aim", "Jump", "Air"),
           "jc": ("Cast Slam Antic", "Cast Slam Antic 2", "Cast Jump", "Jump Aim", "Jump", "Air")}
LOCK_ANY = frozenset(x for v in LOCK_ST.values() for x in v)
WO_TAIL_ST = ("Slam 2", "Slam Effects?", "Slam Recover", "After Scuttle")   # (not Cast 2: its small runes, fp1)
B_FREE_ST = ("Idle", "Walk", "Evade Scuttle", "After Scuttle")


def wall_away(cx: float, hx: float) -> float:
    """A Clapper's centre to the wall on its side away from her (u)."""
    return (cx - WALL_L) if hx >= cx else (WALL_R - cx)


@dataclass
class WoCfg:
    back_u: float = 8.0       # F's back (its centre to the wall on its side away from her) at the start (<=)
    d_u: float = 8.9          # her stand: this far from F's centre on its open side (its Slam Range 8.3 + 0.25 + 0.35)
    draw_u: float = 11.4      # keep standing off while F walks out until its back >= this (the line 6.0 + one slide 5.4:
    #                           a coin evade from there stays outside the line); 0: re-engage at F's first Walk
    end_f: int = 240          # the run ends this long after its start at the latest
    idle_f: int = 90          # ... or this long after F's last Idle entry with F still in Idle
    dash_min: float = 3.0     # a ground dash toward the stand with at least this far to go (3.27 u in 7 frames)
    b_gap: float = 3.5        # no stand within this of B's centre
    open: int = 1             # the opening: wait at c2's landing + d_u (no slash on c2) for its first Idle


@dataclass
class WoRun:
    iid: object
    other: object
    f0: int
    st0: str
    back0: float
    d0: float
    dir: int                   # her side of F (+1 right): the open side
    hp0: int = 0
    opening: bool = False
    phase: str = "out"
    f_idle: int | None = None  # F's last Idle entry
    idles: int = 0
    d_i15: float | None = None # her |dx| from F at its first Idle entry + 15
    walks: int = 0
    back_max: float = 0.0
    sx: float | None = None
    next_st: str | None = None
    k_next: int | None = None
    hp: list = field(default_factory=list)
    dash: int = 0
    keys: int = 0
    f_end: int | None = None
    end: str = ""


@dataclass
class OpCfg:
    back_u: float = 7.1       # c2's back (to the wall on its side away from her) below which no hit on it counts (the
    #                           spec's 7.0: c2 lands at 6.78 - 7.02, fp1 let one slash through at 7.02)
    end_s: float = 8.0        # the rule ends this long after the wake at the latest (else at c2's first move)


@dataclass
class PmCfg:
    ret: int = 1              # 1: herd through one F move (until its next antic / evade); 2: until the lock-bounded run
    #                           check to B passes (TWO_RUNLOCK's)
    d_u: float = 8.3          # F's close slam (she within its Slam Range)
    dy_u: float = 3.9
    hyst: float = 1.0         # F's outer room + this < B's
    room_min: float = 6.0     # F's centre to its wall >= this (slam_play's over_room: she lands behind it)
    stance_u: float = 3.5     # the herd stance: this far from F's centre on its wall side
    wall_pad: float = 1.0
    end_f: int = 360          # the herd lasts at most this long (frames)
    close_u: float = 7.0      # the run check: her within this of B's centre ...
    run_u_s: float = 8.25     # ... at the run speed (u / s), by F's lock end


@dataclass
class PmRun:
    iid: object
    other: object
    f_a: int
    k_a: int
    face: int
    wdir: int                  # toward F's wall (her herd side)
    room_f: float
    room_b: float
    need: float
    lock_rem: float
    hp0: int = 0
    side0: str = "open"        # her side of F at the antic: "open" (between F and B) / "wall" (already behind it)
    kind: str = "slam"         # SP13b: "cast" (TWO_PMCAST's route)
    x0: float | None = None    # (cast) F's x at the antic
    d0: float | None = None    # (cast) her x in front of F at the antic
    f_land: int | None = None  # (cast) frames from the antic to her landing on its wall side
    nat: bool = True           # (cast) the natural gates held (trig force runs them all)
    phase: str = "strike"
    f_herd: int | None = None
    back_herd: float | None = None
    backs: list = field(default_factory=list)   # (frame - f_a, F's wall distance) at F's Idle entries in the herd
    hits_f: int = 0
    hp: list = field(default_factory=list)
    next_st: str | None = None
    f_end: int | None = None
    end: str = ""


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
    casts: int = 1            # 0: slams only (t2 + t3: the slam switches 27 / 27 without HP lost, the cast switches 21 / 29 -
    #                           F's rings at B and B's reaction move together; arm sp9cS)
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
    crit_lead: int = 4        # the other scripts are held off from this many frames before the planned press
    lock_win: int = 10        # F's lock: the press on B's Idle (re-)entry only up to this many frames after it (the
    #                           hit lands 3-4 frames after the press's STATE: before the coin at 15)
    # SP11b TWO_EARLYSWITCH (bigrune answer section 1): the coin needs her within 8.3 u of F at its Idle (+ 0.25 s)
    early: int = 0            # 1: no switch unless her predicted centre at antic frame k_i15 is >= pred_d from F's
    pred_d: float = 8.55      # centre after its lunge (lunge_u along its facing); her: the press point when the run
    lunge_u: float = 3.6      # reaches it by then (the dash held into the sprint, then the walk), else as far as it gets
    k_i15: int = 91           # F's Idle + 15 (Slam 2 at 56 + the tail 20 + the coin 15)


def _asw_cfg() -> AswCfg:
    """SSBOT_FORUM_TWO_ASW_SET="trig=1,back_u=7.5": trial overrides of the AswCfg numbers."""
    return _set_cfg(AswCfg(), "SSBOT_FORUM_TWO_ASW_SET")


def _early_cfg() -> AswCfg:
    """SSBOT_FORUM_TWO_EARLYSWITCH's AswCfg (the spec: casts=0, trig 0, back_u 8.1, first=0, F-B >= 17.1 u, the
    predicted-distance gate); SSBOT_FORUM_TWO_EARLY_SET="back_u=7.5,sep_slam=16" overrides."""
    return _set_cfg(AswCfg(casts=0, trig=0, back_u=8.1, first=0, sep_slam=17.1, early=1), "SSBOT_FORUM_TWO_EARLY_SET")


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
    plan_P: int | None = None                      # ... the planned press (antic frame k) this tick
    hop_w1: int = 0                                # the committed hop's covering windows' end
    k_line: int | None = None  # a slam: the antic frame she was first beyond the hammer line
    k_hold: int | None = None  # the antic frame she first reached the hold / press point
    hit_b: int | None = None   # the first landed hit on B from F's flag-off on (frames - f_off; < 0: in F's lock)
    b_next: str | None = None  # B's next move (state) and its frame - f_off
    k_next: int | None = None
    pd: float | None = None    # SP11b early: her predicted distance from F's lunged centre at antic frame k_i15 (u)
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
    fb: dict | None = None     # SP14 TWO_FLIPB: {"f0", "phase", "k_press", "hook", "ds", "k_ctrl", "k_land", "x_land",
    #                            "out", "end"} (frames - f0)


# ---- SP10c: TWO_JUMPHIT - one Clapper jumps (J), she hits the other one (I) ----
@dataclass
class JhCfg:
    k_land_j: int = 85        # STATE frames from J's Jump Antic entry to its landing (Slam 2): flight from +29 / 30,
    #                           55 frames (SP10b A/B, 149 jumps); after its Jump Aim: the first flight frame + 55
    k_land_c: int = 110       # the jump cast: Cast Slam Antic (+ 2) -> flight from +54-56, 55 frames
    flight_f: int = 55
    back_u: float = 3.0       # the landing's danger behind it (t1: 1.8 u - its Slam 2 body back edge 1.27 + her half
    #                           width + margin - left her under its falling body: 16 of 19 back exits hit by its Air body
    #                           5-15 frames before the landing at -1.1 .. -1.55 u from its centre; it still moves ~0.5 u
    #                           toward the landing in its last 5 frames above her head)
    front_u: float = 8.5      # in front: Slam Collider 2 to 7.76 u + her half width + margin (SP9b t3: 8.3 left her
    #                           7.63 u from the real landing once)
    circle_u: float = 14.3    # the jump cast's rune circle: landing + 6.48 u, r 7.19 (13.67) + half width + margin
    circle_back_u: float = 1.4  # ... its back edge 0.71 u behind the landing + half width + margin
    margin_f: int = 14        # the leave starts this many frames before the walk / run out would just make it (t1: 10,
    #                           the leave's dash came 6-15 frames late after a slash / turn)
    slash_f: int = 14         # a press now ties her up this long (the slash; the hit's recoil a little less)
    dash_u: float = 2.8       # the dash (6 frames, 28 u/s) ...
    dash_f: int = 6
    run_u_s: float = 15.0     # ... then the sprint (u/s; 17.5 at full speed)
    walk_dash_u: float = 2.5  # walk out when the exit is nearer than this
    stop_u: float = 0.35      # the leave walk stops this near the exit (the sprint: + its skid)
    hold_f: int = 8           # at the exit until J's landing + this (the hammer: Slam 2 5-6 frames)
    hold_c_f: int = 90        # the jump cast: until its landing + this (the circle lights 63-86 frames after)
    chase_f: int = 30         # a chase start needs this many frames before the leave
    hit_script: int = 1       # (t2) the hit phase's own script (0: IdleHit and the planner, t1 / t2)


@dataclass
class JhRun:
    J: object                  # the jumper
    I: object                  # the other one (the target)
    kind: str                  # "jump" / "cast"
    f_a: int                   # J's antic entry (the STATE frame - its state time)
    x0: float
    face: int
    d_hj0: float               # her distances at the start (u, centre to centre)
    d_hi0: float
    between: bool
    hp0: int
    phase: str = "hit"         # hit -> leave -> hold -> tail (after J's landing) -> closed
    aim_hx: float | None = None
    f_aim: int | None = None
    land: float | None = None  # J's landing x (from her x at the aim; before it: predicted from her x now)
    f_land_pred: int = 0
    f_land: int | None = None
    side: str | None = None    # the exit: "front" (away from J) / "back" (behind J's landing, under it) / "none"
    exit_x: float | None = None
    f_leave: int | None = None  # the deadline (planned) and the frame the leave began
    k_leave: int | None = None
    k_out: int | None = None   # frames (- f_a) when she was first outside the zone after the leave began
    inside: bool = False       # she is inside the landing zone now
    ldir: int = 0              # the leave's direction (+1 right)
    u_land: float | None = None  # her x from the landing along J's facing at J's landing (+ = in front)
    dash_f: int | None = None
    hits_i: list = field(default_factory=list)   # frames (- f_a) of landed hits on I / on J
    hits_j: list = field(default_factory=list)
    hp: list = field(default_factory=list)       # (frame - f_a, source)
    walk: int = 0
    f_end: int | None = None
    end: str = ""


def _jh_cfg() -> JhCfg:
    """SSBOT_FORUM_TWO_JH_SET="front_u=8.7,margin_f=12": trial overrides of the JhCfg numbers."""
    return _set_cfg(JhCfg(), "SSBOT_FORUM_TWO_JH_SET")


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


def other_danger(s: dict, f_iid, x: float, runes: list | None = None, jump_ok=None, cast_ok: bool = False) -> str | None:
    """Why the Clapper(s) other than f_iid can reach her x now (SP7's _two_danger with her x as the point): a jump move,
    its hammer / lunge within 12.5 u (Slam Antic .. Slam 2: the hammer reaches 12 u in front, from its centre), the small
    runes within 9 u, its recovering body within 4.5 u; a rune circle (lit or to come) over x. jump_ok: the iid whose
    jump move does not count (SP10c TWO_JUMPHIT: its landing guard decides). cast_ok (SP13b TWO_BOMBS2): its small runes
    do not count (the caller plans against its bombs)."""
    for o in _sp.clappers(s):
        if o.get("iid") == f_iid:
            continue
        st = _sp.control(o)[0]
        cx = float(o["pos"][0])
        d = abs(cx - x)
        front = (x - cx) * face_of(o) > -1.5
        if st in JUMP_ST:
            if jump_ok is not None and o.get("iid") == jump_ok:
                continue
            return f"other {st}"
        if st in SLAM_ST and d < _sp.TWO_SLAM_U and front:
            return f"other {st}"
        if st in CAST_ST and d < _sp.TWO_CAST_U and not cast_ok:
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
        self.manual_focus = False                       # explicit manual-B L2 scene owns target/stance preferences
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
        self.rt = _rp.RunePogo() if RUNETIER else None    # SP11a: the pogo tier's controller
        self.claw_req: tuple | None = None   # SP12b: (the caster's iid, its antic entry frame) handed to the Clawline
        self._rt_pend: tuple | None = None   # SP12b: (caster, other, antic entry) - a far cast waiting on the other's slam
        self._claw_n = 0
        self._f_now = 0
        self.esc: EscRun | None = None
        self.esc_done: list[EscRun] = []
        self.esc_n: Counter = Counter()
        self._esc_hop_f: int | None = None   # the hop's latched press frame (mask frame j = 0)
        self._esc_hop_plan: tuple | None = None
        self._sw_stance_x: float | None = None  # arm B's stance this tick (F's flag on)
        self._fb_spot_x: float | None = None    # SP14 TWO_FLIPB: the stance outside the circle
        # SP9c: the antic switch
        self.acfg = _early_cfg() if (EARLY and not ANTICSWITCH) else _asw_cfg() if ASW else AswCfg()
        self.asw: AswRun | None = None
        self.asw_done: list[AswRun] = []
        self.asw_n: Counter = Counter()
        self._asw_dash: dict | None = None    # the dash held into the sprint: {"f0", "dir", "rel", "ctl"}
        self._n_att: Counter = Counter()      # iid -> its attack antics seen (slam / cast / jump / jump cast)
        self._asw_prev = 0                    # its last mask
        # SP11-0: TWO_GUARD's numbers
        self.gcfg = _guard_cfg() if GUARD else GuardCfg()
        # SP10c: TWO_JUMPHIT's run (one Clapper's jump move) and the finished ones
        self.jcfg = _jh_cfg() if JUMPHIT else JhCfg()
        self.jh: JhRun | None = None
        self.jh_done: list[JhRun] = []
        self.jh_n: Counter = Counter()
        self._jh_prev: dict = {}              # iid -> its Control state on the last tick
        self._jh_dash: dict | None = None     # the leave's dash held into the sprint
        self._jh_pressed: int | None = None   # the hit script's last press frame
        # SP11b: TWO_WALKOUT / TWO_OPENPUSH / TWO_PUSHMID (TWO_RUNLOCK lives in gauntlet)
        self.wcfg = _set_cfg(WoCfg(), "SSBOT_FORUM_TWO_WALKOUT_SET") if WALKOUT else WoCfg()
        self.wo: WoRun | None = None
        self.wo_done: list[WoRun] = []
        self.wo_n: Counter = Counter()
        self._wo_cool: dict = {}              # iid -> no new run until its next move (one run per F cycle)
        self._wo_sent = False                 # the run's script sent this tick's keys
        self._wo_pst = None                   # F's state on the run's last tick
        self._focus = None                    # L2's target on the last step
        self.ocfg = _set_cfg(OpCfg(), "SSBOT_FORUM_TWO_OPENPUSH_SET") if OPENPUSH else OpCfg()
        self.op = {"on": False, "end": None, "c2": None, "blk_open": 0, "blk_idle": 0, "nohit": 0, "back": None,
                   "back_end": None, "f_end": None}
        self.pcfg = _set_cfg(PmCfg(), "SSBOT_FORUM_TWO_PUSHMID_SET") if PUSHMID else PmCfg()
        from ssbot.combat import push_cast as _pc
        self.pccfg = _pc.cfg_from_env() if PMCAST else _pc.PcCfg()     # SP13b TWO_PMCAST
        if PMCAST:
            self.pcfg = replace(self.pcfg, ret=self.pccfg.ret)
        self.pm: PmRun | None = None
        self.pm_done: list[PmRun] = []
        self.pm_n: Counter = Counter()
        # SP12a: TWO_RUNEEXIT's numbers and its per-circle log
        self.rcfg = _re_cfg() if RUNEEXIT else ReCfg()
        self.rx_log: dict = {}                # (caster iid, antic clock) -> the circle's record (rune_exit / rx_note)
        self._rx_keys: list = []              # this tick's circles (rx_note)

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
        pm_antics = []
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
            if SP11B and st in MOVE_ST and (pst is None or pst[0] != st):
                self._wo_cool.pop(iid, None)
                if PMANY and st in MOVE_KIND:
                    pm_antics.append(e)
            self.prev[iid] = (st, tin)
            if (SPACE or GUARD) and hx is not None:
                j = self.jumps.get(iid)
                if st in ("Jump Antic", "Cast Slam Antic") and (j is None or j.get("done")):
                    self.jumps[iid] = {"x0": float(e["pos"][0]), "face": face_of(e), "aim_hx": None,
                                       "fam": "jc" if st == "Cast Slam Antic" else "j", "t0": t, "done": False}
                elif j is not None and not j.get("done"):
                    if st in ("Jump", "Air") and j["aim_hx"] is None:
                        j["aim_hx"] = hx
                        if GUARD:
                            j["aim_face"] = face_of(e)     # SP11-0: the jump faces her at its aim
                    if st not in JUMP_ST:
                        j["done"] = True
                        j["land_x"] = float(e["pos"][0])
                        j["t_land"] = t
        if ESC:
            self._esc_observe(f, s, t, hx, antics)
        if ASW:
            self._asw_observe(f, s, t, hx, asw_antics)
        if JUMPHIT:
            self._jh_observe(f, s, hx)
        if SP11B and hx is not None:
            self._sp11b_observe(f, s, t, hx, pm_antics)
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
             two_enc: bool = False, latch=None, sim=None, bombs=None) -> int | None:
        """The mask for frame f + 2 (IdleHit, the Opening, SP9b / SP9c), or None (the planner). latch: m -> the key mask
        the oracle's hold filter latches at f + 2 when m is sent for it (SP9c's dash; None: m)."""
        self.last_part = None                 # SP10a (logging only): which part sent the mask
        if ASW and self.asw is not None:
            am = self._asw_step(f, s, ground, accepting, t, latch)
            if am is not None:
                self._asw_prev = am
                self.last_part = "asw"
                return am
            self._asw_prev = 0
        if ESC and not self.manual_focus and self.esc is not None:
            em = self._esc_step(f, s, ground, accepting, sim, bombs)
            if em is not None:
                self.last_part = "rt" if self.esc is not None and self.esc.mode == "pogo" else "esc"
                return em
        if JUMPHIT and self.jh is not None:
            jm = self._jh_step(f, s, ground, accepting)
            if jm is not None:
                self.last_part = "jh"
                return jm
        if SP11B:
            self._focus = focus
        if WALKOUT:
            wm = self._wo_step(f, s, ground, accepting, focus, two_enc, t)
            self._wo_sent = wm is not None
            if wm is not None:
                self.last_part = "wo"
                return wm
        m = None
        if OPEN and two_enc:
            m = self._open_step(f, s, ground, accepting, t, wake_f)
        idle_m = self._idle_step(f, s, ground, accepting, focus) if IDLEHIT else None
        self.last_part = "open" if m is not None else "idle" if idle_m is not None else None
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
        if (ESC or ASW) and not self.manual_focus:
            v = self.esc_view()
            if v is not None and iid in v["no_hit"]:
                r.why = r.why or "esc"             # SP9b / SP9c: no hit on it now (the corner's wait / F's lock)
                return None
        if SP11B and iid in self.sp11b_nohit(s):
            r.why = r.why or "sp11b"               # SP11b: the opening's push rule / the walk-out's stand-off
            if OPENPUSH and iid == self.op.get("c2"):
                self.op["blk_idle"] += 1
            return None
        k = f - r.f0
        hx = self._xw(s)
        cx = float(F["pos"][0])
        look = 1 if cx > hx else -1
        toward = M_R if look > 0 else M_L
        why = None
        hold_lim = None
        if HOLDHIT and RT2 and self.rt is not None and self.rt.hold_after is not None and self.esc is None \
                and len(self.rt.hold_after) >= 4 and self.rt.hold_after[0] == iid and f <= self.rt.hold_after[1] \
                and self.rt.hold_after[2] is not None:
            # SP12b TWO_HOLDHIT: the held caster - in reach from behind its circle's back edge only
            land, fface = float(self.rt.hold_after[2]), int(self.rt.hold_after[3])
            hold_lim = land - fface * HOLD_HIT_U          # her x may not pass this toward the landing
            if (hx - hold_lim) * fface > 0:
                r.why = r.why or "hold edge"
                return None
        jh = self.jh if (JUMPHIT and self.jh is not None and self.jh.I == iid) else None
        if not accepting:
            why = "no input"
        elif not ground:
            why = "air"
        elif jh is not None and jh.phase != "hit":
            why = "jh leave"                         # SP10c: she leaves J's landing now
        elif jh is not None and jh.f_leave is not None and f + SEND_AHEAD + self.jcfg.slash_f > jh.f_leave:
            why = "jh deadline"                      # SP10c: a press now would still tie her up at the leave
        else:
            why = other_danger(s, iid, hx, self._rune_threats(f, s), jump_ok=jh.J if jh is not None else None)
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
        if hold_lim is not None:
            # (TWO_HOLDHIT) the walk into reach would cross the circle's back edge: the planner
            x_hit = (span[0] - (_sp.SLASH_X[1] - 0.15)) if look > 0 else (span[1] + (_sp.SLASH_X[1] - 0.15))
            if (x_hit - hold_lim) * int(self.rt.hold_after[3]) > 0:
                r.why = r.why or "hold edge"
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
        open_x = OPEN_X
        if WALKOUT and self.wcfg.open and c2 is not None:
            # SP11b TWO_WALKOUT: wait beyond its Slam Range for its first Idle (no slash: it walks out toward her)
            open_x = float(c2["pos"][0]) + self.wcfg.d_u
            o["wo"] = round(open_x, 2)
        elif c2 is not None and ground and st2 in ("Drop In", "Enter Land") and OPENPUSH and (
                wall_away(float(c2["pos"][0]), hx) < self.ocfg.back_u):
            self.op["blk_open"] += 1                # SP11b TWO_OPENPUSH: no front slash on c2 near its wall
        elif c2 is not None and ground and st2 in ("Drop In", "Enter Land"):
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
        if abs(hx - open_x) <= 0.3:
            return 0
        o["walk"] += 1
        return M_L if hx > open_x else M_R

    # ---- SP9b: the escape jump (TWO_CORNER / TWO_WALLSWITCH) ----

    def esc_view(self) -> dict | None:
        """The running escape jump for L2 (gauntlet) and cast_stab: {"iid" (F), "other" (B), "mode", "phase", "kind",
        "hold" (L2's target to keep), "no_hit" (iids whose hits do not count / no IdleHit), "corner_aim" (F's antic:
        the stance in reach), "after_land"}; None without a run the arm took. SP9c: the antic switch's run (mode
        "aswitch") the same way."""
        if ASW and self.asw is not None and self.asw.mode is not None and self.asw.lock_end is None:
            return self._asw_view()
        r = self.esc
        if (r is None or r.mode is None) and RT2 and self.rt is not None and self.rt.hold_after is not None:
            # SP12b: behind the caster's landing - L2 holds the caster (gauntlet's rune hold: BACK_U behind it) to the
            # circle's burst + hold_f
            iid, until = self.rt.hold_after[:2]
            land, fface = (self.rt.hold_after[2:4] if len(self.rt.hold_after) >= 4 else (None, None))
            if self._f_now <= until:
                # no hit on the caster meanwhile (fp1: IdleHit at its Idle and the chase of its evade took her into
                # its circle's back edge, 2 of 15 holds)
                return {"iid": iid, "other": None, "mode": "rt_hold", "phase": "hold", "kind": "cast", "back0": 0.0,
                        "back_u": self.ecfg.back_u, "after_land": True, "corner_aim": False, "hold": iid,
                        "hold_after": True, "no_hit": frozenset() if (HOLDHIT and land is not None) else frozenset({iid}),
                        "land": land, "face": fface}
            self.rt.hold_after = None
        if r is None or r.mode is None:
            return None
        v = {"iid": r.iid, "other": r.other, "mode": r.mode, "phase": r.phase, "kind": r.kind, "back0": r.back0,
             "back_u": self.ecfg.back_u, "after_land": r.f_land is not None, "corner_aim": False,
             "no_hit": frozenset()}
        if r.mode == "pogo":
            # SP11a: L2 holds B through the run (also after F's landing); no hit on B while F's flag is on only with
            # slash=0 (the person: slash it)
            v["hold"] = r.other
            v["hold_after"] = True
            if not self.rt.cfg.slash and r.f_land is None:
                v["no_hit"] = frozenset({r.other})
            return v
        if r.mode == "corner":
            v["hold"] = r.iid
            v["corner_aim"] = r.phase == "antic"
            # (t2) she in the corner (behind F) after its landing: L2 keeps F above the slammer rule (B's slam sent her
            # through F's body twice) and F's dash rows rank after the rest
            v["corner_side"] = r.f_land is not None and r.u_now is not None and r.u_now < 0.0
            if r.phase == "idle" and r.exit in (None, "hop"):
                v["no_hit"] = frozenset({r.iid})          # its Idle: a hit makes it attack her at once, pinned
        elif r.mode == "flipb":
            # SP14 TWO_FLIPB: L2 holds B through the run; the stance outside the circle's far edge once known; hits on
            # B count from F's landing on (B free: its slam is the playbook's)
            v["hold"] = r.other
            v["hold_after"] = True
            if r.f_land is None:
                v["no_hit"] = frozenset({r.other})
            v["stance"] = self._fb_spot_x
        else:
            v["hold"] = r.other
            if r.f_land is None:
                v["no_hit"] = frozenset({r.other})        # F's flag on: a hit on B is cancelled (its coin then)
                v["stance"] = self._sw_stance_x           # short of B / outside F's landing (t1)
        return v

    def _esc_observe(self, f: int, s: dict, t: float, hx: float | None, antics: list) -> None:
        self._f_now = f
        if RT2 and self.claw_req is not None and f - self.claw_req[1] > 3:
            self.claw_req = None                         # SP12b: the Clawline's start is on the antic's first ticks
        cs = _sp.clappers(s)
        hp = int((s.get("hero") or {}).get("health") or 0)
        if RT2 and self._rt_pend is not None:
            self._rt_pend_retry(f, s, cs, hx, hp)
        if self.esc is not None:
            self._esc_update(f, s, hx, hp, cs)
        if self.esc is None and antics and len(cs) == 2 and hx is not None and (self.asw is None
                                                                                 or self.asw.lock_end is not None):
            for e in antics:
                self._esc_start(f, s, e, cs, hx, hp)
                if self.esc is not None:
                    break
        r = self.esc
        if FLIPB and r is not None:
            self._fb_retry(f, s, hx)
        self._fb_spot_x = self._fb_spot(s) if (FLIPB and r is not None and r.mode == "flipb") else None
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
            if RUNETIER and st == "Cast Slam Antic" and self.rt.cfg.scope:
                self._rt_other(f, s, e, o, hx, hp, tin)
            return
        if d > c.d_u or d > do:
            self.esc_n["no_near"] += 1
            if RUNETIER and st == "Cast Slam Antic" and self.rt.cfg.scope:
                self._rt_other(f, s, e, o, hx, hp, tin)
            return
        face = face_of(e)
        kind = "jump" if st == "Jump Antic" else "cast"
        why = self._esc_block(f, s, e, o, hx)
        mode = None
        rt_cast = RUNETIER and kind == "cast"
        if rt_cast:
            # SP11a: the pogo tier on F's escape jump cast (B free, she in front of F, B not on F's body)
            if not why and (hx - cx) * face < 0.5:
                why = "behind"
            if not why and (ox - cx) * face < self.rt.cfg.min_db:
                why = "b near"
            if RT2 and why == "b near":
                why = ""                                 # SP12b: the pass needs no free B
            elif RT2 and (why in ("other casting", "other slamming") or (not why and self._bombs_near(s, hx))):
                # SP12b fp2: B's small runes / its slam (B's hammer hit 1 of 1 such runs) / bombs near her - the run
                # starts once that is over and the bombs are clear of her, while F is still in its antic
                self._rt_pend = (e.get("iid"), o.get("iid"), f - int(round(tin * 60.0)), "esc")
                self.esc_n["rt2_pend_" + ("cast" if why == "other casting" else "slam" if why else "bomb")] += 1
                why = why or "bombs near"
            elif RT2 and why == "behind":
                rt_cast, why = False, ""                 # SP12b: she is behind F already: the default's switch below
                self.esc_n["rt2_behind"] += 1
        if rt_cast:
            if not why:
                mode = "pogo"
            elif ESC_FALLBACK:
                mode, why = "corner", ""                 # TWO_ESC_FALLBACK: the corner takes the rest
                self.esc_n["fallback_corner"] += 1
            if mode == "pogo":
                self.rt.start(f, s, e, o, hx, hp, tin)
        elif not why:
            if ESC_CORNER:
                mode = "corner"
            elif ESC_SWITCH:
                hold = c.sw_hold_j if kind == "jump" else c.sw_hold_c
                if (ox - hx) * face < hold + 0.5:
                    why = "b near"                       # no room to hold short of B (t1: F's landing hammer)
                    if ESC_FALLBACK:
                        mode, why = "corner", ""         # SP9c fallback: the corner takes it
                        self.esc_n["fallback_corner"] += 1
                else:
                    mode = "switch"
        fb = None
        if FLIPB and kind == "cast" and mode in ("switch", None):
            fbw = self._fb_gate(s, e, o, hx)
            self.esc_n[f"fb_{fbw or 'go'}"] += 1
            if not fbw:
                mode, why = "flipb", ""
                air = not _sp.on_ground(s)
                fb = {"f0": f, "phase": "press" if air else "hop",
                      "k_press": (SEND_AHEAD + 1) if air else int(FB["press_k"]), "hook": [], "ds": [],
                      "k_ctrl": None, "k_land": None, "x_land": None, "out": None, "end": "", "late": 0, "air": air}
        self.esc = EscRun(iid=e.get("iid"), other=o.get("iid"), kind=kind, f_a=f,
                          k_a=int(round(tin * 60.0)), x0=round(cx, 3), face=face, back0=round(back, 2),
                          rel0=round((hx - cx) * face, 2), o_st=_sp.control(o)[0], o_d=round(do, 2), mode=mode,
                          hp0=hp, why=why, fb=fb)
        self.esc_n["runs"] += 1
        self.esc_n[f"mode_{mode}"] += 1
        if why:
            self.esc_n[f"no_switch_{why}"] += 1

    def _rt_other(self, f: int, s: dict, e: dict, o: dict, hx: float, hp: int, tin: float, pend=None) -> None:
        """SP11a scope 1 (the lead's NOTE 7): a jump cast that is not the focus's escape jump - the pogo tier on the
        other Clapper (its face, its head) when that one is free, in front of the caster by min_db and no rune circle
        lies over her / it; declined: counted only (no escape run: the default play)."""
        ost = _sp.control(o)[0]
        ox, cx = float(o["pos"][0]), float(e["pos"][0])
        face = face_of(e)
        why = ""
        if ost in JUMP_ST:
            why = "other jumping"
        elif ost in CAST_ST:
            why = "other casting"
        elif ost in SLAM_ST or ost == "Slam Recover":
            why = "other slamming"
        elif (ox - cx) * face < self.rt.cfg.min_db:
            why = "b near"
        elif any(a < max(hx, ox) + 3.0 and b > min(hx, ox) - 3.0 for a, b in self._rune_threats(f, s)):
            why = "rune"
        if RT2 and (why == "b near" or (why == "other slamming" and ost == "Slam Recover")):
            why = ""                                     # SP12b: the pass needs no free target
        if RT2 and not why and pend is None and self._bombs_near(s, hx):
            why = "bombs near"                           # SP12b fp2: 2 far-cast runs hit at their start by lit bombs
        if RT2 and not why and pend is None and not _sp.on_ground(s):
            why = "air"                                  # SP12b fp3: 4 of 5 failed far runs began airborne (the pogo
            #                                              planner on her focus, no pass from the air)
        if RT2 and why in ("other slamming", "other casting", "bombs near", "air") and self.rt.cfg.other_slam \
                and pend is None:
            # SP12b: the other one (her focus) slams - the playbook takes its slam - or casts small runes (fp2: the
            # default and the low hop take them); the run starts once that is over while the caster is still in its
            # antic (the retry in _esc_observe)
            self._rt_pend = (e.get("iid"), o.get("iid"), f - int(round(tin * 60.0)), "other")
            self.esc_n["rt2_pend_" + ("slam" if why == "other slamming" else "cast" if why == "other casting"
                                      else "air" if why == "air" else "bomb")] += 1
        if pend is not None:
            self.esc_n["rt2_pend_start" if not why else "rt2_pend_no"] += 1
            if why:
                return
        self.esc_n["rt_other"] += 1
        if why:
            self.esc_n[f"rt_other_no_{why}"] += 1
            return
        if RT2 and self.rt.cfg.claw and pend is None and self._claw_band(s, e, o, hx):
            # SP12b (the lead's 05:06 note): the far one's cast in the Clawline band to claw_chase (variant A); claw=2
            # alternates with the pass per cast (the fixed point's comparison)
            n = self._claw_n
            self._claw_n += 1
            if self.rt.cfg.claw == 1 or n % 2 == 0:
                self.claw_req = (e.get("iid"), f - int(round(tin * 60.0)))
                self.esc_n["rt2_claw_n"] += 1
                # L2 holds the caster through its circle after the Clawline (she lands behind its landing)
                self.rt.hold_after = (e.get("iid"), f - int(round(tin * 60.0)) + 108 + self.rt.cfg.lit1
                                      + self.rt.cfg.hold_f)
                self.rt.claw_runs.append({"f_a": f, "iid": e.get("iid"), "d0": round(abs(hx - cx), 2)})
                return
            self.esc_n["rt2_claw_alt_pass"] += 1
        self.rt.start(f, s, e, o, hx, hp, tin, src="other")
        self.esc = EscRun(iid=e.get("iid"), other=o.get("iid"), kind="cast", f_a=f, k_a=int(round(tin * 60.0)),
                          x0=round(cx, 3), face=face, back0=round(back_room(e), 2), rel0=round((hx - cx) * face, 2),
                          o_st=ost, o_d=round(abs(hx - ox), 2), mode="pogo", hp0=hp, why="")
        self.esc_n["runs"] += 1
        self.esc_n["mode_pogo_other"] += 1

    def _rt_pend_retry(self, f: int, s: dict, cs: list, hx: float | None, hp: int) -> None:
        """SP12b: a far cast declined while her focus slammed - start its run once that slam is over (Slam Recover /
        no longer slamming) while the caster is still in its antic, no other run on; else drop it."""
        jid, oid, f_a, src = self._rt_pend
        e, o = clapper_by(s, jid), clapper_by(s, oid)
        st = _sp.control(e)[0] if e is not None else None
        if e is None or o is None or st not in ("Cast Slam Antic", "Cast Slam Antic 2") or hx is None \
                or f - f_a > self.rt.cfg.pend_f:
            self._rt_pend = None
            return
        ost = _sp.control(o)[0]
        held = self.esc is not None and not (self.esc.mode is None and self.esc.iid == jid)
        if held or ost in SLAM_ST or ost in CAST_ST or (src == "other" and not _sp.on_ground(s)):
            return
        if self._bombs_near(s, hx):
            return                                   # bombs still near her (they light outward ~1.7 s)
        self._rt_pend = None
        if self.esc is not None:
            self._esc_close(f, "rt2 pend")           # the caster's declined escape record: the run replaces it
        if src == "esc":
            tin = (f - f_a) / 60.0
            self.esc_n["rt2_pend_start"] += 1
            self.rt.start(f, s, e, o, hx, hp, tin)
            cx, ox = float(e["pos"][0]), float(o["pos"][0])
            self.esc = EscRun(iid=e.get("iid"), other=o.get("iid"), kind="cast", f_a=f, k_a=int(round(tin * 60.0)),
                              x0=round(cx, 3), face=face_of(e), back0=round(back_room(e), 2),
                              rel0=round((hx - cx) * face_of(e), 2), o_st=ost, o_d=round(abs(hx - ox), 2),
                              mode="pogo", hp0=hp, why="")
            self.esc_n["runs"] += 1
            self.esc_n["mode_pogo"] += 1
            return
        self._rt_other(f, s, e, o, hx, hp, (f - f_a) / 60.0, pend=(jid, f_a))

    def _bombs_near(self, s: dict, hx: float | None) -> bool:
        """SP12b: a small-rune bomb (appeared or lit) within pend_bomb_u of her."""
        if hx is None:
            return False
        from ssbot.combat import rune_bombs as _rbm
        return any(abs(bx - hx) < self.rt.cfg.pend_bomb_u for _, bx, _, _ in _rbm.bomb_ents(s.get("ents")))

    def rt_hold_block(self, f: int) -> str | None:
        """SP12b: why no chase (evade_chase) may run now - L2 holds a jump caster through its circle (rt_hold)."""
        if RT2 and self.rt is not None and self.rt.hold_after is not None and self.esc is None \
                and f <= self.rt.hold_after[1]:
            return "rt hold"
        return None

    @staticmethod
    def _claw_band(s: dict, e: dict, o: dict, hx: float) -> bool:
        """SP12b: a far cast the late Clawline can take (claw_chase's gates: 8.4-12.2 u, she in front of it on the
        ground, silk, the other one not in the way)."""
        from ssbot.combat import claw_chase as _cc
        c = _cc.ClawCfg()
        cx = float(e["pos"][0])
        h = s.get("hero") or {}
        if (hx - cx) * face_of(e) <= 0 or not c.d_min <= abs(hx - cx) <= c.d_max:
            return False
        if not _sp.on_ground(s) or int(h.get("silk") or 0) < 1:
            return False
        return not _cc.ClawChase._in_way(hx, cx, o)

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

    def _fb_gate(self, s: dict, e: dict, o: dict, hx: float) -> str:
        """SP14 TWO_FLIPB: why F's escape jump cast is not flipped over B ("" when it is)."""
        from ssbot.combat import jump_behind as _jbm
        from ssbot.combat import rune_bombs as _rbm
        h = s.get("hero") or {}
        cx, ox = float(e["pos"][0]), float(o["pos"][0])
        face = face_of(e)
        ost = _sp.control(o)[0]
        if (hx - cx) * face <= 0.5 or (ox - hx) * face <= 0:
            return "not between"
        if (ost in JUMP_ST or ost in CAST_ST or ost in SLAM_ST or ost in ("Evade Scuttle",)) and ost not in FB_OK_B:
            return "b busy"
        if not _sp.on_ground(s):
            yb = self._fb_throw_y(s)
            if yb is None or yb > FB["air_yb"]:
                return "air"
        if int(h.get("silk") or 0) < 1 or not ((h.get("can") or {}).get("harpoon", True)):
            return "silk"
        front = ox - face * (2.25 + HALF_W)                  # B's front edge (it faces her) + her half width
        gap = (front - hx) * face
        if not 0.5 <= gap <= FB["gap_max"]:
            return "b far" if gap > 0 else "b near"
        lo, hi = min(hx, ox) - 3.0, max(hx, ox) + 3.0
        if any(lo < bx < hi for _, bx, _, _ in _rbm.bomb_ents(s.get("ents"))):
            return "bombs"
        far_now = _jbm.landing(cx, hx, face) + face * 13.67
        if FB["trig"] != "force" and (front - 0.5 - far_now) * face > 0:
            return "room short of b"                         # she can stand outside the circle short of B
        x_aim = front - face * 2.0                           # her x at F's aim: the hook's stop short of B's body
        far = _jbm.landing(cx, x_aim, face) + face * 13.67
        spot = far + face * (HALF_W + FB["out_m"])
        back_b = ox + face * (1.34 + HALF_W + 1.2)
        spot = max(spot, back_b) if face > 0 else min(spot, back_b)
        wall = WALL_R if face > 0 else WALL_L
        if (wall - face * 0.5 - spot) * face < 0:
            return "no room past b"
        return ""

    @staticmethod
    def _fb_throw_y(s: dict) -> float | None:
        """SP14 TWO_FLIPB: her box bottom above the floor at a Clawline thrown now (CLAWSTRIKE's fit; None: vy out of
        the fit's range)."""
        h = s.get("hero") or {}
        b = h.get("box")
        if not b:
            return None
        y = float(b[1]) - (_sp.FLOOR_Y - 1.56)
        vy = float((h.get("vel") or [0.0, 0.0])[1])
        if not -6.0 <= vy <= 9.0:
            return None
        return y - 0.261 + 0.0788 * vy

    def _fb_retry(self, f: int, s: dict, hx: float | None) -> None:
        """SP14 TWO_FLIPB (fpfb1): F's escape jump cast not flipped at its first STATE - the gate again every tick of its
        antic to k_late; a pass turns the run into "flipb" (in the air: no hop)."""
        r = self.esc
        if hx is None or r.fb is not None or r.kind != "cast" or r.mode not in ("switch", None) or r.phase != "antic":
            return
        if f - r.f_a + r.k_a > FB["k_late"]:
            return
        e, o = clapper_by(s, r.iid), clapper_by(s, r.other)
        if e is None or o is None:
            return
        why = self._fb_gate(s, e, o, hx)
        if why:
            return
        air = not _sp.on_ground(s)
        r.mode, r.why = "flipb", ""
        r.fb = {"f0": f, "phase": "press" if air else "hop", "k_press": (SEND_AHEAD + 1) if air else int(FB["press_k"]),
                "hook": [], "ds": [], "k_ctrl": None, "k_land": None, "x_land": None, "out": None, "end": "",
                "late": f - r.f_a + r.k_a, "air": air}
        self.esc_n["fb_retry_go"] += 1

    def _fb_spot(self, s: dict) -> float | None:
        """SP14 TWO_FLIPB: the stance just outside the circle's far edge (its landing as predicted at F's aim / seen),
        past B's back when B stands there."""
        r = self.esc
        o = clapper_by(s, r.other)
        land = r.x_land if r.x_land is not None else r.land_pred
        if land is None:
            return None
        spot = land + r.face * (13.67 + HALF_W + FB["out_m"])
        if o is not None:
            ox = float(o["pos"][0])
            lo, hi = body_span(o)
            if lo - HALF_W - 0.3 < spot < hi + HALF_W + 0.3:
                spot = (hi + HALF_W + 0.5) if r.face > 0 else (lo - HALF_W - 0.5)
            del ox
        return min(max(spot, WALL_L + 0.5), WALL_R - 0.5)

    def _flipb_step(self, f: int, s: dict, ground: bool, accepting: bool) -> int | None:
        """SP14 TWO_FLIPB's keys (module note at FLIPB): hop, turn, Clawline at B, lock, drift past B with down slashes
        on its head, until she lands; None after (the planner, L2's stance outside the circle)."""
        r = self.esc
        fb = r.fb
        if fb["phase"] in ("out", "done"):
            return None
        o = clapper_by(s, r.other)
        if o is None:
            fb.update(phase="done", end="B gone")
            return None
        k = f + SEND_AHEAD - fb["f0"]
        h = s.get("hero") or {}
        hx = _sp.hero_x(s)
        ox = float(o["pos"][0])
        toward = M_R if ox > hx else M_L
        away = M_R if r.face > 0 else M_L                    # from F toward B's far side
        for ev in s.get("ev") or ():
            d = ev.get("d") or {}
            if ev.get("k") == "hit" and d.get("type_key") == CLAPPER and (d.get("ent") or d.get("iid")) == r.other \
                    and "Harpoon" in str(d.get("src") or ""):
                fb["hook"].append(k)
        if r.hp and r.hp[-1] >= 0 and fb["phase"] in ("hop", "press", "lock") and r.hp[-1] >= k - 3 - SEND_AHEAD:
            fb.update(phase="out", end="hurt")
            return None
        ph = fb["phase"]
        if ph == "hop":
            if k < int(FB["hop_hold"]):
                return M_J
            fb["phase"] = ph = "press"
        if ph == "press":
            kp = fb["k_press"]
            if k < kp - 1:
                return 0
            if k == kp - 1:
                return toward
            if k < kp + 2:
                return M_CLAW | toward
            fb["phase"] = ph = "lock"
        if ph == "lock":
            clip = str((h.get("anim") or {}).get("clip") or "")
            if (accepting and not clip.startswith("Harpoon") and k > fb["k_press"] + 12) or k > fb["k_press"] + 45:
                fb.update(phase="after", k_ctrl=k)
                ph = "after"
            else:
                return 0
        if ph == "after":
            if ground and k > fb["k_ctrl"] + 3:
                fb.update(phase="out", k_land=k, x_land=round(hx, 2), end="landed")
                return None
            if k > fb["k_ctrl"] + 90:
                fb.update(phase="out", end="timeout")
                return None
            tm = h.get("tm") or {}
            ready = float(tm.get("atk_cd") or 0.0) * 60.0 - (SEND_AHEAD - 1) <= 0.05
            y = float((h.get("box") or [0, 0])[1]) - (_sp.FLOOR_Y - 1.56)
            y0, y1 = body_y(o)
            top = y1 - (_sp.FLOOR_Y - 1.56)
            if (len(fb["ds"]) < int(FB["ds_max"]) and ready and abs(ox - hx) <= FB["ds_reach"]
                    and 0.0 <= y - top <= FB["ds_top"] and (not fb["ds"] or k - fb["ds"][-1] > 6)):
                fb["ds"].append(k)
                return _sp.M_D | M_A | away
            return away
        return None

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
        if r.mode == "pogo":
            if self.rt.run is not None:
                self.rt.update(f, s, hx, hp)
            if self.rt.run is None:
                self._esc_close(f, f"rt {self.rt.done[-1].end}" if self.rt.done else "rt")
            return
        if r.mode == "flipb":
            if o is None:
                self._esc_close(f, "B dead")
            elif r.f_land is not None and ("burst" in r.rune and f - r.f_land - r.rune["burst"] > FB["end_f"]
                                           or f - r.f_land > 150):
                if r.fb is not None and hx is not None:
                    o_ = clapper_by(s, r.other)
                    r.fb["out"] = round((hx - (r.x_land + r.face * 13.67)) * r.face, 2) if r.x_land is not None else None
                    del o_
                self._esc_close(f, "flipb end")
            return
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
        if self.rt is not None and self.rt.run is not None:
            self.rt.close(f, why)                           # SP11a: the tier's run ends with the escape run
        if r is not None:
            r.f_end, r.end = f - r.f_a, why
            self.esc_done.append(r)
            self.esc_n[f"end_{why}"] += 1
        self.esc = None
        self._esc_hop_f = None

    def _esc_step(self, f: int, s: dict, ground: bool, accepting: bool, sim=None, bombs=None) -> int | None:
        r = self.esc
        if r is None or r.mode is None:
            return None
        if r.mode == "pogo":
            m = self.rt.step(f, s, ground, accepting, sim, bombs)
            if self.rt.run is None:
                self._esc_close(f, f"rt {self.rt.done[-1].end}" if self.rt.done else "rt")
            return m
        if r.mode == "corner":
            return self._corner_step(f, s, ground, accepting)
        if r.mode == "flipb":
            return self._flipb_step(f, s, ground, accepting)
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

    def rt_critical(self) -> bool:
        """SP11a: the pogo tier's run holds the keys (the policy steps no other script). SP14: TWO_FLIPB's keys too."""
        if (FLIPB and self.esc is not None and self.esc.mode == "flipb" and self.esc.fb is not None
                and self.esc.fb["phase"] in ("hop", "press", "lock", "after")):
            return True
        return RUNETIER and self.rt is not None and self.esc is not None and self.esc.mode == "pogo"             and self.rt.critical()

    def esc_stats(self) -> dict:
        runs = self.esc_done + ([self.esc] if self.esc is not None else [])
        out = dict(self.esc_n)
        if RUNETIER and self.rt is not None:
            out["rune_tier"] = self.rt.stats()
            if RT2:
                out["rt2_claw"] = list(self.rt.claw_runs)
        out["esc_runs"] = [{"f_a": r.f_a, "kind": r.kind, "mode": r.mode, "why": r.why, "back0": r.back0,
                            "rel0": r.rel0, "k_a": r.k_a, "o_st": r.o_st, "o_d": r.o_d,
                            "take": None if r.f_take is None else r.f_take - r.f_a,
                            "land": None if r.f_land is None else r.f_land - r.f_a,
                            "idle": None if r.f_idle is None else r.f_idle - r.f_a, "u_land": r.u_land,
                            "hits_f": r.hits_f, "hits_b": r.hits_b, "hp": r.hp, "exit": r.exit, "hop": r.hop,
                            "press": {k: v for k, v in (r.press or {}).items() if k != "pf"} if r.press else None,
                            "rune": r.rune, "walk": r.walk, "f_end": r.f_end, "end": r.end, "fb": r.fb} for r in runs]
        return out

    # ---- SP10c: TWO_JUMPHIT (one Clapper jumps: hit the other one, out of the landing before it lands) ----

    def _jh_observe(self, f: int, s: dict, hx: float | None) -> None:
        """Every tick: the run's bookkeeping, or a new run on the first STATE of a Clapper's Jump Antic / Cast Slam
        Antic with both live (not the focus's escape jump at its wall: SP9b's)."""
        cs = _sp.clappers(s)
        if self.jh is not None:
            self._jh_update(f, s, hx, cs)
        prev = self._jh_prev
        now = {e.get("iid"): _sp.control(e)[0] for e in cs}
        self._jh_prev = now
        if (self.jh is not None and self.jh.phase != "tail") or len(cs) != 2 or hx is None:
            return
        for e in cs:
            st, tin = _sp.control(e)
            if st not in ESC_ANTIC or prev.get(e.get("iid")) in ESC_PRE:
                continue
            if self.jh is not None:
                if e.get("iid") == self.jh.J:
                    continue
                self._jh_close(f, "next")                # J's tail: the other one's jump starts a new run
            o = next(x for x in cs if x.get("iid") != e.get("iid"))
            self.jh_n["antics"] += 1
            cx, ox = float(e["pos"][0]), float(o["pos"][0])
            d, do = abs(hx - cx), abs(hx - ox)
            c = self.ecfg
            if back_room(e) <= c.back_u and d <= c.d_u and d <= do:
                self.jh_n["no_escape"] += 1              # SP9b's (the switch / the corner)
                continue
            if _sp.control(o)[0] in JUMP_ST:
                self.jh_n["no_other_jumping"] += 1
                continue
            if (ESC and self.esc is not None) or (ASW and self.asw is not None and self.asw.lock_end is None):
                self.jh_n["no_run"] += 1
                continue
            hp = int((s.get("hero") or {}).get("health") or 0)
            self.jh = JhRun(J=e.get("iid"), I=o.get("iid"), kind="jump" if st == "Jump Antic" else "cast",
                            f_a=f - int(round(tin * 60.0)), x0=round(cx, 3), face=face_of(e), d_hj0=round(d, 2),
                            d_hi0=round(do, 2), between=min(cx, ox) < hx < max(cx, ox), hp0=hp)
            self.jh_n["runs"] += 1
            self.jh_n[f"runs_{self.jh.kind}"] += 1
            self._jh_update(f, s, hx, cs)
            break

    @staticmethod
    def _landing(x0: float, aim_x: float, face: int) -> float:
        """gauntlet.jump_landing (forum.md 10.1): its x + 0.92 clamp(her x - 5 u on its side - its x, +-12)."""
        return x0 + 0.92 * max(-12.0, min(12.0, aim_x - face * 5.0 - x0))

    def _jh_zone(self, r: JhRun, land: float) -> tuple[float, float]:
        c = self.jcfg
        front = c.front_u if r.kind == "jump" else c.circle_u
        a, b = land - r.face * c.back_u, land + r.face * front
        return min(a, b), max(a, b)

    def _jh_frames(self, dist: float, dash: bool) -> float:
        """Frames to cover dist (u): the walk, or one dash held into the ground sprint (cast_stab.sprint_travel)."""
        c = self.jcfg
        if not dash or dist < c.walk_dash_u:
            return max(0.0, dist) / WALK_U
        jmax = _cs.DASH_F + self.acfg.grace_f + 1
        for j in range(1, jmax + 1):
            if _cs.sprint_travel(j) >= dist:
                return float(j) + 4.0                    # + the stop (control back after the sprint's release)
        return jmax + 4.0 + (dist - _cs.sprint_travel(jmax)) / WALK_U

    def _jh_exit(self, r: JhRun, s: dict, hx: float, land: float, J: dict, I: dict, dash: bool):
        """The way out of the landing zone: (side, x, frames) - the front (away from J; not through I's body or a wall)
        or the back (behind its landing, under J in the air; not through J's body while it is still on the ground)."""
        c = self.jcfg
        lo, hi = self._jh_zone(r, land)
        out = []
        for side, x in (("front", (hi + 0.15) if r.face > 0 else (lo - 0.15)),
                        ("back", (lo - 0.15) if r.face > 0 else (hi + 0.15))):
            if not WALL_L + 0.6 <= x <= WALL_R - 0.6:
                continue
            a, b = min(hx, x), max(hx, x)
            ia, ib = body_span(I)
            if ia - HALF_W - 0.15 < b and ib + HALF_W + 0.15 > a:
                continue                                 # through I's body
            if side == "back" and _sp.control(J)[0] in ESC_PRE:
                ja, jb = body_span(J)
                if ja - HALF_W - 0.15 < b and jb + HALF_W + 0.15 > a:
                    continue                             # through J's body on the ground (its antic)
            out.append((side, x, self._jh_frames(abs(x - hx), dash)))
        if not out:
            return None
        return min(out, key=lambda o: o[2])

    def _jh_update(self, f: int, s: dict, hx: float | None, cs: list) -> None:
        c = self.jcfg
        r = self.jh
        J, I = clapper_by(s, r.J), clapper_by(s, r.I)
        for ev in s.get("ev") or ():
            d = ev.get("d") or {}
            if ev.get("k") == "hit" and d.get("type_key") == CLAPPER and (d.get("dealt") is None
                                                                       or float(d.get("dealt")) > 0):
                who = d.get("ent") or d.get("iid")
                if who == r.I:
                    r.hits_i.append(f - r.f_a)
                elif who == r.J:
                    r.hits_j.append(f - r.f_a)
            elif ev.get("k") == "hp" and (d.get("delta") or 0) < 0:
                r.hp.append((f - r.f_a, str(d.get("source"))[:40]))
        if J is None or I is None or hx is None:
            self._jh_close(f, "gone")
            return
        st = _sp.control(J)[0]
        if r.aim_hx is None and st in FLIGHT_ST:
            # Jump Aim is instant (never a tick's state): her x on its first flight STATE (one frame after the aim)
            vx = float(((s.get("hero") or {}).get("vel") or [0.0, 0.0])[0])
            r.aim_hx = round(hx - vx / 60.0, 3)
            r.f_aim = f
            r.land = round(self._landing(r.x0, r.aim_hx, r.face), 3)
        if st in LAND_ST and r.f_land is None:
            r.f_land = f
            r.u_land = round((hx - float(J["pos"][0])) * r.face, 2)
            if r.phase == "hit":
                r.phase = "tail"
        if st not in ESC_PRE + FLIGHT_ST + LAND_ST:
            self._jh_close(f, "done")
            return
        if r.phase == "tail" or (r.f_land is not None and r.phase == "hold" and f - r.f_land > (
                c.hold_f if r.kind == "jump" else c.hold_c_f)):
            r.phase = "tail"
            r.inside = False
            return
        land = r.land if r.land is not None else self._landing(r.x0, hx, r.face)
        lo, hi = self._jh_zone(r, land)
        r.inside = lo < hx < hi
        if r.inside and r.k_leave is not None:
            r.k_out = None
        elif not r.inside and r.k_leave is not None and r.k_out is None:
            r.k_out = f - r.f_a
        if r.phase != "hit":
            if r.phase == "leave" and r.f_aim is not None and r.side is not None and r.exit_x is not None:
                # the exit from the aim's landing (the leave may have begun from the predicted one)
                if r.side == "front":
                    r.exit_x = round((hi + 0.15) if r.face > 0 else (lo - 0.15), 3)
                else:
                    r.exit_x = round((lo - 0.15) if r.face > 0 else (hi + 0.15), 3)
            return
        f_land = (r.f_aim + c.flight_f) if r.f_aim is not None else (r.f_a + (c.k_land_j if r.kind == "jump"
                                                                               else c.k_land_c))
        r.f_land_pred = f_land
        if not r.inside:
            r.f_leave = None
            return
        can = (s.get("hero") or {}).get("can") or {}
        ex = self._jh_exit(r, s, hx, land, J, I, bool(can.get("dash", True)))
        if ex is None:
            r.f_leave = None
            r.side = "none"
            return
        side, x, n = ex
        r.f_leave = int(f_land - n - c.margin_f)
        if r.f_aim is not None and f + SEND_AHEAD >= r.f_leave:
            # (before the aim the landing follows her x: no leave then)
            r.phase, r.side, r.exit_x, r.k_leave = "leave", side, round(x, 3), f - r.f_a
            r.ldir = 1 if x > hx else -1
            self.jh_n[f"leave_{side}"] += 1

    def _jh_close(self, f: int, why: str) -> None:
        r = self.jh
        if r is not None:
            r.f_end, r.end = f, why
            self.jh_done.append(r)
            self.jh_n[f"end_{why}"] += 1
        self.jh = None
        self._jh_dash = None

    def _jh_step(self, f: int, s: dict, ground: bool, accepting: bool) -> int | None:
        """The leave: one dash held into the ground sprint toward the exit when it is farther than walk_dash_u (released
        by her x and speed, then no key until control returns), the walk the rest, then no key at the exit until J's
        landing + hold_f (the jump cast: its circle); None in the other phases (IdleHit / the planner at I)."""
        r = self.jh
        c = self.jcfg
        if r.phase == "leave" and r.f_land is not None:
            r.phase = "hold"
        if r.phase == "hit" and c.hit_script:
            return self._jh_hit(f, s, ground, accepting)
        if r.phase not in ("leave", "hold") or r.exit_x is None:
            return None
        h = s.get("hero") or {}
        tm = h.get("tm") or {}
        clip = str((h.get("anim") or {}).get("clip") or "")
        hx = _sp.hero_x(s)
        dm = getattr(self, "_jh_dash", None)
        if dm is not None:
            j = f + SEND_AHEAD - dm["f0"]
            sg = 1 if dm["dir"] == M_R else -1
            if dm.get("rel") is None:
                v = abs(float((h.get("vel") or [0.0, 0.0])[0]))
                remain = (r.exit_x - hx) * sg
                if j > _cs.DASH_F and (remain - self.acfg.release_lag * v / 60.0 <= 0.3
                                       or j > _cs.DASH_F + self.acfg.grace_f):
                    dm["rel"] = j
                    return 0
                return dm["dir"] | M_DASH
            if ground and accepting and clip != "Dash" and not clip.startswith(_cs.STOP_WAIT_CLIPS):
                self._jh_dash = None
            elif j > dm["rel"] + 40:
                self._jh_dash = None
            else:
                return 0
        if not accepting:
            return None
        dist = abs(r.exit_x - hx)
        toward = M_R if r.exit_x > hx else M_L
        if dist <= c.stop_u or (hx - r.exit_x) * r.ldir >= 0:
            return 0                                     # at (or past) the exit: stand
        can_dash = bool(((h.get("can") or {}).get("dash", True)))
        if (dist >= c.walk_dash_u and r.dash_f is None and float(tm.get("dash_cd") or 0.0) <= 0.02 and can_dash
                and not any(x in clip for x in NO_ATK_CLIPS) and self._facing(s, 1 if toward == M_R else -1)):
            # (t1: ground only - in the air she walked out; the air dash: 0.15 s at 28 u/s, then the direction key)
            self._jh_dash = {"f0": f + SEND_AHEAD, "dir": toward, "rel": None} if ground else None
            r.dash_f = f - r.f_a
            self.jh_n["dash" if ground else "air_dash"] += 1
            return toward | M_DASH
        r.walk += 1
        return toward

    def _jh_hit(self, f: int, s: dict, ground: bool, accepting: bool) -> int | None:
        """The hit phase (t2: the planner floated on the umbrella / stood off in 30 of 39 runs - J's predicted landing
        follows her - and landed 0.87 hits on I per run): to I and slash it - the side slash when it meets I's body
        (the turn key first), else the walk toward it (in the air: the key toward it without the jump key, she drops);
        near the leave's deadline she stands; the planner while I itself can reach her (its own move's tail, a rune
        circle) or without input."""
        r = self.jh
        c = self.jcfg
        sec = self._second(f)
        if sec is not None and self._jh_pressed == self._press_f:
            return sec
        I = clapper_by(s, r.I)
        if I is None or not accepting:
            return None
        hx = self._xw(s)
        if other_danger(s, r.J, hx, self._rune_threats(f, s)) is not None:
            self.jh_n["hit_danger"] += 1
            return None
        if r.f_leave is not None and f + SEND_AHEAD + c.slash_f > r.f_leave:
            return 0 if ground else None                 # the leave is due: stand (the leave script next)
        cx = float(I["pos"][0])
        look = 1 if cx > hx else -1
        toward = M_R if look > 0 else M_L
        span = body_span(I)
        if not ground:
            r.walk += 1
            return toward if not slash_meets(hx, look, span, spare=-0.4) else 0
        if slash_meets(hx, look, span):
            if not self._atk_ready(s):
                return 0
            if not self._facing(s, look):
                return toward
            self._jh_pressed = f
            self.jh_n["hit_press"] += 1
            return self._press(f, toward)
        r.walk += 1
        return toward

    def jh_view(self) -> dict | None:
        """TWO_JUMPHIT's run for L2 (gauntlet): {"J", "I", "phase", "kind", "exit", "side", "hold" (L2's target),
        "no_hit"}; None without a run (or after a back exit's landing: she is at J, the normal rule)."""
        r = self.jh
        if r is None:
            return None
        if r.phase == "tail" and r.side == "back":
            return None
        v = {"J": r.J, "I": r.I, "phase": r.phase, "kind": r.kind, "exit": r.exit_x, "side": r.side, "hold": r.I,
             "no_hit": frozenset()}
        if r.phase in ("leave", "hold"):
            v["no_hit"] = frozenset({r.I, r.J})
        return v

    def jh_block(self, f: int) -> str | None:
        """Why a chase (evade_chase) on I may not run now (SP10c): the leave, or too near its deadline."""
        r = self.jh
        if r is None or r.phase == "tail":
            return None
        if r.phase != "hit":
            return "jh leave"
        if r.f_leave is not None and f + self.jcfg.chase_f > r.f_leave:
            return "jh deadline"
        return None

    def jh_stats(self) -> dict:
        runs = self.jh_done + ([self.jh] if self.jh is not None else [])
        out = dict(self.jh_n)
        out["jh_runs"] = [{"f_a": r.f_a, "J": r.J, "I": r.I, "kind": r.kind, "d_hj0": r.d_hj0, "d_hi0": r.d_hi0,
                           "between": r.between, "aim": None if r.f_aim is None else r.f_aim - r.f_a,
                           "aim_hx": r.aim_hx, "land": r.land, "f_land": None if r.f_land is None else r.f_land - r.f_a,
                           "f_land_pred": r.f_land_pred - r.f_a if r.f_land_pred else None, "side": r.side,
                           "exit": r.exit_x, "k_leave": r.k_leave, "k_out": r.k_out, "u_land": r.u_land,
                           "dash": r.dash_f, "walk": r.walk, "hits_i": r.hits_i, "hits_j": r.hits_j, "hp": r.hp,
                           "f_end": None if r.f_end is None else r.f_end - r.f_a, "end": r.end} for r in runs]
        return out

    # ---- SP9c: the antic switch (TWO_ANTICSWITCH) ----

    def asw_skip(self) -> frozenset:
        """F while the antic switch runs: the slam playbook and the low hop leave its move alone."""
        r = self.asw
        return frozenset({r.iid}) if (ASW and r is not None and r.mode is not None and r.lock_end is None
                                      ) else frozenset()

    def asw_critical(self) -> bool:
        """The bomb hop's press is due within crit_lead frames, or it is committed (its hold, the covering bombs' lit
        window): the antic switch's script keeps the keys ahead of the other scripts (like the low hop's critical
        window). (t2, c3e0f5f: a 40-frame window after the press kept the slam playbook off B's slam: its hammer, 4 HP
        losses in sp9cP)"""
        r = self.asw
        if not ASW or r is None or r.mode is None:
            return False
        if r.hop_P is None:
            return r.plan_P is not None and r.plan_P - r.k_now <= self.acfg.crit_lead
        return r.k_now <= max(r.hop_P + r.hop_H + 1, r.hop_w1 + 1)

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
            r.plan_P = None
            if r.pending and r.hop_P is None and _sp.on_ground(s):
                from ssbot.combat import rune_lowhop as _rl
                plan = _rl.hop_plan(thr, r.k_now, range(9, 17), 3)
                r.plan_P = None if plan is None else int(plan["P"])

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
        if kind == "cast" and not c.casts:
            self.asw_n["no_cast_off"] += 1
            return
        k_now = int(round(tin * 60.0))
        ost = _sp.control(o)[0]
        sep = abs(ox - cx)
        why = ""
        early_pd = None
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
            if not why and c.early:
                # SP11b: her centre at F's Idle + 15 (antic frame k_i15) >= pred_d from F's centre after its lunge
                press = self._asw_press_x(o, face)
                dist = (press - hx) * face
                n = c.k_i15 - k_now - SEND_AHEAD
                if dist <= 0 or frames(dist) <= n:
                    hp_x = press
                elif dist < c.dash_min:
                    hp_x = hx + face * max(0, n) * WALK_U
                else:
                    jj = max(0, min(n, jmax))
                    hp_x = hx + face * (_cs.sprint_travel(jj) + max(0, n - jj) * WALK_U)
                pd = (hp_x - (cx + face * c.lunge_u)) * face
                early_pd = round(pd, 2)
                if pd < c.pred_d:
                    why = "pred"
        run = AswRun(iid=e.get("iid"), other=o.get("iid"), kind=kind, f_a=f, k_a=k_now, ta=t - tin, x0=round(cx, 3),
                     face=face, back0=round(back, 2), pred=round(pr, 2), sep0=round(sep, 2),
                     rel0=round((hx - cx) * face, 2), o_st=ost, o_d=round(do, 2), mode=None if why else "aswitch",
                     hp0=hp, why=why, o_prev=ost, pd=early_pd)
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
                r.hop_P, r.hop_H, r.hop_w1 = k, plan["H"], max(w1 for _, w1, _ in thr)
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
                            "bombs_live": sum(1 for b in r.bombs.values() if not b["stale"]),
                            **({"pd": r.pd, "o_iid": r.other, "iid": r.iid} if EARLY else {})} for r in runs]
        return out

    # ---- SP11b: TWO_WALKOUT / TWO_OPENPUSH / TWO_PUSHMID ----

    def _sp11b_observe(self, f: int, s: dict, t: float, hx: float, pm_antics: list) -> None:
        cs = _sp.clappers(s)
        hp = int((s.get("hero") or {}).get("health") or 0)
        if WALKOUT and self.wo is not None:
            self._wo_update(f, s, t, hx, hp, cs)
        if OPENPUSH:
            self._op_update(f, s, hx, cs)
        if PMANY:
            if self.pm is not None:
                self._pm_update(f, s, t, hx, hp, cs)
            if self.pm is None and pm_antics and (len(cs) == 2 or (PMCAST and self.pccfg.trig == "force")):
                for e in pm_antics:
                    if PMCAST and _sp.control(e)[0] == "Spell Antic":
                        self._pmc_start(f, s, e, cs, hx, hp)
                    elif len(cs) == 2:
                        self._pm_start(f, s, e, cs, hx, hp)
                    if self.pm is not None:
                        break

    def _busy(self) -> bool:
        """Another two-Clapper run holds the play (the antic switch, the escape run, TWO_JUMPHIT, PUSHMID)."""
        return ((ASW and self.asw is not None and self.asw.mode is not None)
                or (ESC and self.esc is not None and self.esc.mode is not None)
                or (JUMPHIT and self.jh is not None) or (PMANY and self.pm is not None))

    def sp11b_nohit(self, s: dict) -> frozenset:
        """The Clappers whose hits do not count now: OPENPUSH's c2 near its wall in the opening, WALKOUT's F."""
        out = set()
        if OPENPUSH and self.op["on"] and self.op["end"] is None and self.op.get("c2") is not None:
            c2 = clapper_by(s, self.op["c2"])
            hx = _sp.hero_x(s)
            if c2 is not None and hx >= float(c2["pos"][0]) and wall_away(float(c2["pos"][0]), hx) < self.ocfg.back_u:
                out.add(self.op["c2"])
        if WALKOUT and self.wo is not None:
            out.add(self.wo.iid)
        return frozenset(out)

    def sp11b_prefs(self, prefs, s: dict):
        """SP11b's changes to L2's prefs (before TWO_SPACE's stance): the no-hit Clappers, WALKOUT's stand, PUSHMID's
        herd stance."""
        if not ((s.get("hero") or {}).get("box") or (s.get("hero") or {}).get("pos")):
            return prefs
        nh = self.sp11b_nohit(s)
        if nh:
            if OPENPUSH and self.op.get("c2") in nh:
                self.op["nohit"] += 1
            prefs = replace(prefs, no_hit=frozenset(prefs.no_hit) | nh)
        if WALKOUT and self.wo is not None and self.wo.sx is not None:
            prefs = replace(prefs, stance_x=float(self.wo.sx))
        if (PMANY and self.pm is not None and self.pm.phase == "herd"
                and getattr(prefs, "target", None) == self.pm.iid):
            x = self._pm_stance(s)
            if x is not None:
                prefs = replace(prefs, stance_x=float(x))
        return prefs

    # -- TWO_OPENPUSH --

    def _op_update(self, f: int, s: dict, hx: float, cs: list) -> None:
        o = self.op
        if o["end"] is not None:
            return
        if not o["on"]:
            if self.open.get("f_wake") is None or len(cs) != 2:
                return
            o["on"] = True
            o["f0"] = f
            c2 = min(cs, key=lambda e: float(e["pos"][0]))
            o["c2"] = c2.get("iid")
            o["back"] = round(wall_away(float(c2["pos"][0]), hx), 2)
        c2 = clapper_by(s, o["c2"])
        if c2 is None:
            o["end"], o["f_end"] = "gone", f - o["f0"]
            return
        st = _sp.control(c2)[0]
        o["back_end"] = round(wall_away(float(c2["pos"][0]), hx), 2)
        if st in MOVE_ST:
            o["end"], o["f_end"], o["move"] = "move", f - o["f0"], st
        elif (f - o["f0"]) / 60.0 > self.ocfg.end_s:
            o["end"], o["f_end"] = "time", f - o["f0"]

    # -- TWO_WALKOUT --

    def _wo_start(self, f: int, s: dict, focus, two_enc: bool, t: float) -> None:
        c = self.wcfg
        cs = _sp.clappers(s)
        if len(cs) != 2 or self._busy():
            return
        hx = _sp.hero_x(s)
        F = clapper_by(s, focus) if focus is not None else None
        opening = (two_enc and c.open and self.open.get("done") == "c2 idle" and self.open.get("wo") is not None
                   and not self.wo_n.get("runs_open", 0))
        if opening:
            F = min(cs, key=lambda e: float(e["pos"][0]))     # c2 (its first Idle)
        if F is None:
            F = min(cs, key=lambda e: abs(float(e["pos"][0]) - hx))
        iid = F.get("iid")
        if self._wo_cool.get(iid):
            return
        st = _sp.control(F)[0]
        if not (st in WO_TAIL_ST or (st == "Idle" and (iid in self.entry or opening))):
            return
        o = next(x for x in cs if x.get("iid") != iid)
        cx, ox = float(F["pos"][0]), float(o["pos"][0])
        back = wall_away(cx, hx)
        if back > c.back_u or abs(hx - cx) > c.d_u + 2.0:
            return                                       # (beyond d_u + 2 she is not at it: its walk comes anyway)
        self.wo_n["cand"] += 1
        d = 1 if hx >= cx else -1
        why = None
        ost = _sp.control(o)[0]
        sx = min(max(cx + d * c.d_u, WALL_L + 0.5), WALL_R - 0.5)
        if ost not in B_FREE_ST:
            why = "b busy"
        elif self._wo_bombs(s, hx) or self._wo_bombs(s, sx):
            why = "bomb"
        elif abs(sx - ox) < c.b_gap or (sx - cx) * d < c.d_u - 0.5:
            why = "no stand"
        elif GUARD and guard_hit(self.guard_spans(f, s, t), sx - HALF_W, sx + HALF_W, own=iid) is not None:
            why = "guard"
        if why is not None:
            self.wo_n[f"no_{why}"] += 1
            self._wo_cool[iid] = True
            return
        hp = int((s.get("hero") or {}).get("health") or 0)
        self.wo = WoRun(iid=iid, other=o.get("iid"), f0=f, st0=str(st), back0=round(back, 2),
                        d0=round(abs(hx - cx), 2), dir=d, hp0=hp, opening=bool(opening), sx=sx,
                        back_max=round(back, 2))
        if st == "Idle":
            self.wo.f_idle, self.wo.idles = f, 1
        self._wo_cool[iid] = True
        self._wo_pst = st
        self.wo_n["runs"] += 1
        if opening:
            self.wo_n["runs_open"] += 1

    def _wo_update(self, f: int, s: dict, t: float, hx: float, hp: int, cs: list) -> None:
        r = self.wo
        c = self.wcfg
        F, o = clapper_by(s, r.iid), clapper_by(s, r.other)
        if hp < r.hp0:
            r.hp.append(f - r.f0)
            self._wo_close(f, "hurt")
            return
        if F is None or o is None:
            self._wo_close(f, "gone")
            return
        st = _sp.control(F)[0]
        cx = float(F["pos"][0])
        back = (cx - WALL_L) if r.dir > 0 else (WALL_R - cx)
        r.back_max = round(max(r.back_max, back), 2)
        if r.iid in self.entry:
            r.idles += 1
            r.f_idle = f
        if r.f_idle is not None and r.d_i15 is None and f - r.f_idle >= 15:
            r.d_i15 = round(abs(hx - cx), 2)
        if st == "Walk" and self._wo_pst != "Walk":
            r.walks += 1
        self._wo_pst = st
        ost = _sp.control(o)[0]
        sx = min(max(cx + r.dir * c.d_u, WALL_L + 0.5), WALL_R - 0.5)
        r.sx = sx
        if st in MOVE_ST:
            r.next_st, r.k_next = st, f - (r.f_idle if r.f_idle is not None else r.f0)
            self._wo_close(f, "f move")
        elif self._wo_bombs(s, hx):
            self._wo_close(f, "bomb")                  # (fp1: 2 of 19 runs hurt by F's small runes from a Cast 2 start)
        elif ost not in B_FREE_ST:
            self._wo_close(f, "b move")
        elif c.draw_u <= 0 and r.walks > 0:
            self._wo_close(f, "walked")
        elif c.draw_u > 0 and back >= c.draw_u:
            self._wo_close(f, "drawn")
        elif abs(sx - float(o["pos"][0])) < c.b_gap or (sx - cx) * r.dir < c.d_u - 1.0:
            self._wo_close(f, "no stand")
        elif f - r.f0 > c.end_f:
            self._wo_close(f, "time")
        elif st == "Idle" and r.f_idle is not None and f - r.f_idle > c.idle_f:
            self._wo_close(f, "idle")

    @staticmethod
    def _wo_bombs(s: dict, hx: float) -> bool:
        """A small-rune bomb (lit or to light) within its radius + 1.5 u of her x: the low hop's / the planner's."""
        from ssbot.combat import rune_bombs as _rb
        return any(abs(bx - hx) < _rb.R + 1.5 for _, bx, _, _ in _rb.bomb_ents(s.get("ents")))

    def _wo_close(self, f: int, why: str) -> None:
        r = self.wo
        if r is not None:
            r.f_end, r.end = f - r.f0, why
            self.wo_done.append(r)
            self.wo_n[f"end_{why}"] += 1
        self.wo = None
        self._wo_pst = None

    def wo_yield(self, f: int) -> None:
        """Another script took the keys: the walk-out ends."""
        if self.wo is not None:
            self._wo_close(f, "yield")

    def _wo_step(self, f: int, s: dict, ground: bool, accepting: bool, focus, two_enc: bool, t: float) -> int | None:
        if self.wo is None:
            self._wo_start(f, s, focus, two_enc, t)
        r = self.wo
        if r is None or not accepting or not ground:
            return None
        h = s.get("hero") or {}
        tm = h.get("tm") or {}
        clip = str((h.get("anim") or {}).get("clip") or "")
        F = clapper_by(s, r.iid)
        if F is None or r.sx is None:
            return None
        hx = _sp.hero_x(s)
        dist = r.sx - self._xw(s)
        cx = float(F["pos"][0])
        look = 1 if cx > hx else -1
        r.keys += 1
        if abs(dist) <= 0.3:
            if r.phase == "out":
                r.phase = "hold"
            if not self._facing(s, look) and "Dash" not in clip:
                return M_R if look > 0 else M_L        # face it (one frame: 0.14 u)
            return 0
        toward = M_R if dist > 0 else M_L
        if (abs(dist) >= self.wcfg.dash_min and float(tm.get("dash_cd") or 0.0) <= 0.02
                and not any(x in clip for x in NO_ATK_CLIPS) and (hx - cx) * r.dir < self.wcfg.d_u - 3.0):
            r.dash += 1
            self.wo_n["dash"] += 1
            return toward | M_DASH
        return toward

    # -- TWO_PUSHMID --

    @staticmethod
    def _pm_lock_rem(kind: str, k_now: int) -> float:
        return max(0.0, (LOCK_F[kind] - k_now - SEND_AHEAD) / 60.0)

    def _pm_start(self, f: int, s: dict, e: dict, cs: list, hx: float, hp: int) -> None:
        c = self.pcfg
        st, tin = _sp.control(e)
        kind = MOVE_KIND[st]
        self.pm_n[f"{kind}_antics"] += 1
        o = next(x for x in cs if x.get("iid") != e.get("iid"))
        cx, ox = float(e["pos"][0]), float(o["pos"][0])
        d, do = abs(hx - cx), abs(hx - ox)
        hy = float(((s.get("hero") or {}).get("pos") or [0.0, 0.0])[1])
        if d > do or d > c.d_u or abs(hy - float(e["pos"][1])) > c.dy_u:
            return
        face = face_of(e)
        room_f = (cx - WALL_L) if ox > cx else (WALL_R - cx)     # its outer room (away from B)
        room_b = (ox - WALL_L) if cx > ox else (WALL_R - ox)
        if room_f + c.hyst >= room_b:
            return
        self.pm_n[f"{kind}_trig"] += 1
        k_now = int(round(tin * 60.0))
        need = max(0.0, do - c.close_u) / c.run_u_s
        lock_rem = self._pm_lock_rem(kind, k_now)
        wdir = 1 if cx > ox else -1                              # toward F's outer wall
        why = None
        if kind != "slam":
            why = kind
        elif self._busy():
            why = "busy"
        elif (hx - cx) * face <= 0:
            why = "behind"                                       # she is not in front of it
        elif _sp.control(o)[0] not in ("Idle", "Walk"):
            why = "b busy"
        elif need <= lock_rem:
            why = "run ok"                                       # the switch's run fits: not PUSHMID's case
        elif room_f < c.room_min:
            why = "room"
        if why is not None:
            self.pm_n[f"no_{why}"] += 1
            return
        self.pm = PmRun(iid=e.get("iid"), other=o.get("iid"), f_a=f, k_a=k_now, face=face, wdir=wdir,
                        room_f=round(room_f, 2), room_b=round(room_b, 2), need=round(need, 3),
                        lock_rem=round(lock_rem, 3), hp0=hp, side0="wall" if (hx - cx) * wdir > 0 else "open")
        self.pm_n["runs"] += 1
        self.pm_n[f"runs_{self.pm.side0}"] += 1         # "wall": she is on F's wall side already (the way out keeps it)

    def _pm_update(self, f: int, s: dict, t: float, hx: float, hp: int, cs: list) -> None:
        r = self.pm
        c = self.pcfg
        F, o = clapper_by(s, r.iid), clapper_by(s, r.other)
        if hp < r.hp0:
            r.hp.append((f - r.f_a, r.phase))
        r.hp0 = hp
        if F is None or (o is None and not (r.kind == "cast" and r.other is None)):
            self._pm_close(f, "gone")
            return
        st, tin = _sp.control(F)
        cx = float(F["pos"][0])
        wall_d = (cx - WALL_L) if r.wdir < 0 else (WALL_R - cx)
        side = (hx - cx) * r.wdir > 0.3                          # she is on F's wall side
        for ev in s.get("ev") or ():
            d = ev.get("d") or {}
            if (ev.get("k") == "hit" and d.get("type_key") == CLAPPER and (d.get("ent") or d.get("iid")) == r.iid
                    and r.phase == "herd" and (d.get("dealt") is None or float(d.get("dealt")) > 0)):
                r.hits_f += 1
        if r.phase == "strike" and r.kind == "cast":
            # (SP13b TWO_PMCAST) the crossing: the low hop's over plan; landed on F's wall side -> the herd
            if f - r.f_a > 170:
                self._pm_close(f, "no herd")
            elif _sp.on_ground(s) and side and f - r.f_a > 20:
                r.phase, r.f_herd, r.back_herd = "herd", f, round(wall_d, 2)
                r.f_land = f - r.f_a
                self.pm_n["herd"] += 1
            elif _sp.on_ground(s) and not side and st not in CAST_ST:
                self._pm_close(f, "no cross")
            return
        if r.phase == "strike":
            if f - r.f_a > 140:
                self._pm_close(f, "no herd")
            elif st not in SLAM_ST + ("Slam Recover",) and _sp.on_ground(s):
                if side:
                    r.phase, r.f_herd, r.back_herd = "herd", f, round(wall_d, 2)
                    self.pm_n["herd"] += 1
                else:
                    self._pm_close(f, "no cross")
            return
        if r.iid in self.entry:
            r.backs.append((f - r.f_a, round(wall_d, 2)))
        if not side and _sp.on_ground(s):
            self._pm_close(f, "crossed")
            return
        kind = MOVE_KIND.get(st)
        if st in MOVE_ST and tin * 60.0 <= 3.5 and r.next_st is None:
            r.next_st = st                                       # its next antic / evade (its first STATE)
            if c.ret == 1:
                self._pm_close(f, "f move")
                return
        if c.ret == 2 and kind is not None and st in LOCK_ST[kind] and o is not None:
            need = max(0.0, abs(hx - float(o["pos"][0])) - c.close_u) / c.run_u_s
            if need <= self._pm_lock_rem(kind, int(round(tin * 60.0))):
                self._pm_close(f, "run ok")
                return
        if f - (r.f_herd or r.f_a) > c.end_f:
            self._pm_close(f, "time")

    def _pmc_start(self, f: int, s: dict, e: dict, cs: list, hx: float, hp: int) -> None:
        """SP13b TWO_PMCAST: F's close Spell Antic -> a cast-route run (PmRun kind "cast") when its gates hold (trig nat:
        PUSHMID's - she nearer F, F's outer room + hyst < B's, B idle / walking and out of the lock-bounded run's reach;
        trig force: only she in front within d_max, room_c behind F, no other run)."""
        c, pc = self.pcfg, self.pccfg
        st, tin = _sp.control(e)
        k_now = int(round(tin * 60.0))
        self.pm_n["cast_antics"] += 1
        cx = float(e["pos"][0])
        face = face_of(e)
        d = (hx - cx) * face
        wdir = -face                                             # F's back: away from her (she is in front)
        room = (cx - WALL_L) if wdir < 0 else (WALL_R - cx)
        hy = float(((s.get("hero") or {}).get("pos") or [0.0, 0.0])[1])
        o = next((x for x in cs if x.get("iid") != e.get("iid")), None)
        why = None
        if self._busy():
            why = "busy"
        elif d <= 0:
            why = "behind"
        elif d > pc.d_max or abs(hy - float(e["pos"][1])) > c.dy_u:
            why = "far"
        elif room < pc.room_c:
            why = "room"
        elif o is not None and _sp.control(o)[0] in JUMP_ST:
            why = "b jump"                                       # (fp2) B in a jump move: its landing / circle
        else:
            # (fp2) a big rune circle (lit or to come) over her way: from her x to F's far side's landing band
            lo_x, hi_x = sorted((hx, cx + wdir * (pc.land_hi + HALF_W)))
            if any(x0 < hi_x and x1 > lo_x for x0, x1 in self._rune_threats(f, s)):
                why = "circle"
        nat_why, room_b, need, lock_rem = None, 0.0, 0.0, self._pm_lock_rem("cast", k_now)
        if o is None:
            nat_why = "one"
        else:
            ox = float(o["pos"][0])
            do = abs(hx - ox)
            room_b = (ox - WALL_L) if cx > ox else (WALL_R - ox)
            need = max(0.0, do - c.close_u) / c.run_u_s
            if abs(hx - cx) > do:
                nat_why = "b nearer"
            elif (ox - cx) * wdir > 0:
                nat_why = "b behind f"                           # B on F's back side: its wall side is not outer
            elif room + c.hyst >= room_b:
                nat_why = "f room"
            elif _sp.control(o)[0] not in ("Idle", "Walk"):
                nat_why = "b busy"
            elif need <= lock_rem:
                nat_why = "run ok"
        if why is None and nat_why is not None and pc.trig != "force":
            why = nat_why
        if why is not None:
            self.pm_n[f"cno_{why}"] += 1
            return
        self.pm = PmRun(iid=e.get("iid"), other=None if o is None else o.get("iid"), f_a=f, k_a=k_now, face=face,
                        wdir=wdir, room_f=round(room, 2), room_b=round(room_b, 2), need=round(need, 3),
                        lock_rem=round(lock_rem, 3), hp0=hp, side0="open", kind="cast", x0=round(cx, 3),
                        d0=round(d, 3), nat=nat_why is None)
        self.pm_n["cast_runs"] += 1
        self.pm_n["cast_runs_nat" if nat_why is None else "cast_runs_forced"] += 1

    def pm_note(self, f: int, why: str) -> None:
        """SP13b: the low hop gave the cast route up (no over plan by k_last, lost in the air): the run ends."""
        if self.pm is not None and self.pm.kind == "cast" and self.pm.phase == "strike":
            self._pm_close(f, why)

    def _pm_close(self, f: int, why: str) -> None:
        r = self.pm
        if r is not None:
            r.f_end, r.end = f - r.f_a, why
            self.pm_done.append(r)
            self.pm_n[f"end_{why}"] += 1
        self.pm = None

    def _pm_stance(self, s: dict) -> float | None:
        r = self.pm
        F = clapper_by(s, r.iid)
        if F is None:
            return None
        cx = float(F["pos"][0])
        room = (WALL_R - cx) if r.wdir > 0 else (cx - WALL_L)
        u = min(self.pcfg.stance_u, max(0.0, room - self.pcfg.wall_pad))
        if u < 1.0:
            u = room / 2.0
        return cx + r.wdir * u

    def pm_view(self) -> dict | None:
        """PUSHMID for L2 (gauntlet): {"hold": F, "phase", "iid", "other"} while the run is on, else None."""
        r = self.pm
        if not PMANY or r is None:
            return None
        return {"hold": r.iid, "phase": r.phase, "iid": r.iid, "other": r.other}

    def pm_cast(self) -> dict:
        """SP13b TWO_PMCAST for the low hop: {F's iid: the world side to cross to (its wall side)} while the cast
        route's crossing is due."""
        r = self.pm
        if not PMCAST or r is None or r.kind != "cast" or r.phase != "strike":
            return {}
        return {r.iid: r.wdir}

    def pm_hint(self) -> dict:
        """PUSHMID for the slam playbook: {F's iid: the world side to land on (its wall side)} in the strike."""
        r = self.pm
        if not PUSHMID or r is None or r.phase != "strike" or r.kind != "slam":
            return {}
        return {r.iid: r.wdir}

    def sp11b_stats(self) -> dict:
        out = {}
        if WALKOUT:
            runs = self.wo_done + ([self.wo] if self.wo is not None else [])
            out["walkout"] = {**dict(self.wo_n), "runs_rec": [
                {"f0": r.f0, "iid": r.iid, "st0": r.st0, "back0": r.back0, "d0": r.d0, "opening": r.opening,
                 "f_idle": None if r.f_idle is None else r.f_idle - r.f0, "idles": r.idles, "d_i15": r.d_i15,
                 "walks": r.walks, "back_max": r.back_max, "next_st": r.next_st, "k_next": r.k_next, "hp": r.hp,
                 "dash": r.dash, "keys": r.keys, "f_end": r.f_end, "end": r.end} for r in runs]}
        if OPENPUSH:
            out["openpush"] = dict(self.op)
        if PMANY:
            runs = self.pm_done + ([self.pm] if self.pm is not None else [])
            out["pushmid"] = {**dict(self.pm_n), "runs_rec": [
                {"f_a": r.f_a, "iid": r.iid, "k_a": r.k_a, "side0": r.side0,
                 **({"kind": r.kind, "x0": r.x0, "d0": r.d0, "f_land": r.f_land, "nat": r.nat} if PMCAST else {}), "room_f": r.room_f, "room_b": r.room_b, "need": r.need,
                 "lock_rem": r.lock_rem, "f_herd": None if r.f_herd is None else r.f_herd - r.f_a,
                 "back_herd": r.back_herd, "backs": r.backs, "hits_f": r.hits_f, "hp": r.hp, "next_st": r.next_st,
                 "f_end": r.f_end, "end": r.end} for r in runs]}
        return out

    # ---- SP11-0 TWO_GUARD ----

    def guard_spans(self, f: int, s: dict, t: float) -> list:
        """SSBOT_FORUM_TWO_GUARD: [(lo, hi, kind, iid)] - every live Clapper's danger spans now (the consumers skip
        their own Clapper's): "land" its jump's landing band from its Jump Aim (jump_landing from its take-off x and her
        x at the aim, its facing then) to its landing + land_tail_f, "rune" its jump cast's circle from the aim (the
        circle predicted from the landing) and every circle object lit or still to come (cast_stab.rune_spans; owner
        None), "hammer" a slam (Slam Antic: both sides - the antic turns to her; Slam 0 .. Slam 2: in front), "body" its
        body. Two live Clappers only (else [])."""
        cs = _sp.clappers(s)
        if len(cs) != 2:
            return []
        c = self.gcfg
        out = []
        for e in cs:
            iid = e.get("iid")
            st = _sp.control(e)[0]
            cx, fc = float(e["pos"][0]), face_of(e)
            a, b = body_span(e)
            out.append((a - c.body_pad, b + c.body_pad, "body", iid))
            j = self.jumps.get(iid)
            jland = None
            landed = j is not None and j.get("done") and j.get("t_land") is not None
            if j is not None and j.get("aim_hx") is not None:
                if not j.get("done"):
                    from ssbot.combat.tactics.gauntlet import jump_landing
                    jf = j.get("aim_face", j["face"])
                    jland = (jump_landing(j["x0"], j["aim_hx"], jf), jf)
                elif landed and (t - j["t_land"]) * 60.0 <= c.land_tail_f:
                    jland = (float(j["land_x"]), j.get("aim_face", j["face"]))
            if jland is not None:
                L, jf = jland
                p, q = L - jf * c.land_back, L + jf * c.land_front
                out.append((min(p, q), max(p, q), "land", iid))
                if j.get("fam") == "jc" and not j.get("done"):
                    cc = L + jf * c.rune_c
                    out.append((cc - c.rune_r, cc + c.rune_r, "rune", iid))
            elif st in SLAM_ST and not (landed and (t - j["t_land"]) * 60.0 <= c.land_tail_f + 6):
                if st == "Slam Antic":
                    out.append((cx - c.hammer_u, cx + c.hammer_u, "hammer", iid))
                else:
                    p, q = cx - fc * c.hammer_back, cx + fc * c.hammer_u
                    out.append((min(p, q), max(p, q), "hammer", iid))
        for lo, hi in self._rune_threats(f, s):
            out.append((lo - HALF_W - 0.3, hi + HALF_W + 0.3, "rune", None))
        return out

    # ---- SP12a TWO_RUNEEXIT ----

    def rune_exit(self, f: int, s: dict, t: float) -> tuple:
        """SSBOT_FORUM_TWO_RUNEEXIT: (circles, bodies, numbers) for the planner's exit tier, frames from this tick's
        clock t: circles [(centre x, reach, first lit frame, last lit frame)] of every jump cast past its Jump Aim or
        landed whose circle is still to light (not seen burst) within horizon_f; bodies [(lo, hi, from frame)] - a
        grounded Clapper's body span now, a jumper's around its landing from its landing - jump_block_f. () without
        a circle. Logs each circle (rx_log)."""
        cs = _sp.clappers(s)
        c = self.rcfg
        self._rx_keys = []
        circles, bodies = [], []
        from ssbot.combat.tactics.gauntlet import jump_landing
        spans = _cs.rune_spans(s)
        hx = _sp.hero_x(s) if (s.get("hero") or {}).get("box") or (s.get("hero") or {}).get("pos") else None
        for e in cs:
            iid = e.get("iid")
            st = _sp.control(e)[0]
            j = self.jumps.get(iid)
            k_land = None
            if j is not None and j.get("aim_hx") is not None:
                jf = j.get("aim_face", j["face"])
                if not j.get("done"):
                    L = jump_landing(j["x0"], j["aim_hx"], jf)
                    k_land = (j["t0"] + c.land_f / 60.0 - t) * 60.0
                elif j.get("t_land") is not None:
                    L = float(j["land_x"])
                    k_land = (j["t_land"] - t) * 60.0
                if k_land is not None and j.get("fam") == "jc":
                    k_on, k_off = k_land + c.lit_f, k_land + c.end_f
                    cx = L + jf * (c.c_right if jf > 0 else c.c_left)
                    key = (iid, round(float(j["t0"]), 3))
                    rec = self.rx_log.get(key)
                    burst = rec is not None and rec.get("burst")
                    if not burst and rec is not None:
                        # the circle object near the centre seen lit, then unlit: burst
                        for lo, hi, _ciid, lit in spans:
                            if abs(0.5 * (lo + hi) - cx) < 1.5:
                                if lit:
                                    rec["lit"] = True
                                elif rec.get("lit"):
                                    rec["burst"] = burst = True
                    if not burst and k_off > 0 and k_on <= c.horizon_f:
                        circles.append((cx, c.reach, k_on, k_off))
                        if rec is None:
                            rec = self.rx_log[key] = {"iid": iid, "t0": round(float(j["t0"]), 3), "f0": f,
                                                      "cx": round(cx, 2), "L": round(float(L), 2), "face": jf,
                                                      "k_on0": round(k_on, 1), "hx0": None if hx is None else round(hx, 2),
                                                      "ticks": 0, "inside": 0, "split": 0, "chosen_late": 0,
                                                      "f_split0": None, "f_last": f, "lit": False, "burst": False}
                        rec["f_last"] = f
                        rec["ticks"] += 1
                        if hx is not None and abs(hx - cx) < c.reach:
                            rec["inside"] += 1
                        self._rx_keys.append(key)
            if (st in JUMP_ST and st not in ("Jump Antic", "Cast Slam Antic", "Cast Slam Antic 2")
                    and k_land is not None and j is not None and not j.get("done")):
                bodies.append((L - c.jump_body, L + c.jump_body, k_land - c.jump_block_f))
            else:
                a, b = body_span(e)
                bodies.append((a - c.body_pad, b + c.body_pad, -1e9))
        if not circles:
            return ()
        return (tuple(circles), tuple(bodies), {"v": c.v, "buf_f": c.buf_f, "wall_pad": c.wall_pad})

    def rx_note(self, f: int, info) -> None:
        """SSBOT_FORUM_TWO_RUNEEXIT: the planner's exit tier this tick (planner.last_info["rx"]: [safe rows late, safe
        rows, chosen late]) on this tick's circles."""
        if not info or not self._rx_keys:
            return
        n_late, n_safe, ch_late = info
        for key in self._rx_keys:
            rec = self.rx_log.get(key)
            if rec is None:
                continue
            if 0 < n_late < n_safe:
                rec["split"] += 1
                if rec["f_split0"] is None:
                    rec["f_split0"] = f
            rec["chosen_late"] += int(bool(ch_late))

    # ---- S5 the stance ----

    def space(self, prefs, s: dict, t: float, focus):
        """TWO_SPACE (module docstring b-d): the stance moved out of the forbidden spans."""
        if self.manual_focus:
            return prefs                                # physical hazards remain in the planner/native checks
        if SP11B:
            prefs = self.sp11b_prefs(prefs, s)
        if not SPACE:
            return prefs
        cs = _sp.clappers(s)
        if len(cs) != 2 or not ((s.get("hero") or {}).get("box") or (s.get("hero") or {}).get("pos")):
            return prefs
        hx = _sp.hero_x(s)
        x = float(prefs.stance_x)
        jh = self.jh if JUMPHIT else None
        if jh is not None and jh.phase in ("leave", "hold") and jh.exit_x is not None:
            # SP10c: out of J's landing zone (the leave script walks there; the planner's stance the same)
            self.space_n["jh exit"] += 1
            return replace(prefs, stance_x=float(jh.exit_x))
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
            if jh is not None and jh.J == e.get("iid") and jh.phase == "hit" and jh.inside:
                corner_own = True                # SP10c: at I until the leave (its deadline keeps her clear)
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
        if JUMPHIT:
            res["jumphit"] = self.jh_stats()
        if SP11B:
            res.update(self.sp11b_stats())
        if RUNEEXIT:
            res["rune_exit"] = list(self.rx_log.values())    # SP12a
        return res


def intro_keys(s: dict) -> int:
    """SSBOT_FORUM_TWO_OPEN: the harness's key mask in the wave-start intro (the load -> the wave's activation): left
    while her x is right of OPEN_INTRO_X, else none."""
    h = s.get("hero") or {}
    if not (h.get("box") or h.get("pos")) or not h.get("hero_accepting_input", True):
        return 0
    return M_L if _sp.hero_x(s) > OPEN_INTRO_X else 0

