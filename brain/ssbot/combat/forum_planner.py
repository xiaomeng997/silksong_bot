"""The Forum's fast layer (forum_planner_plan §4.1 / §4.4 items 2-3 / §4.5, round R3): the L1 planner over the
MultiForecast, with the Forum vocabulary and a two-stage check that keeps the tick in budget. The Bell Beast planner
(combat.planner.Planner) is not touched: ForumPlanner is its subclass, the Forum switch is which class the glue makes.

Per tick (the lexicographic order and every rule of Planner.tick unless named here):
  candidates  the posture family of the start state (ground / air / wall: candidates.build_forum; T = 36 frames, the
              0.6 s horizon of §4.5) = the core evasion set (56 rows: wait, move, 3 jump holds x 3 ways, dash either
              way, each with idle / run either way / a full jump) + the posture's attack pieces x every continuation,
              plus CONTINUE (the previous plan carried on); without control (hit-stop, recoil, a lock: the keys only
              queue) the core rows alone.
  stage 1     every row rolled out on the nominal lane only; its box centre against the support (MultiForecast
              .occupied: the templates are dilated by the hero hurtbox, so this is the nominal box's exact test).
              Necessary: a row in contact here is in contact in stage 2 too (the hull holds the nominal box, the hull
              test is conservative for its sub-boxes, frames invulnerable in every lane are invulnerable in the
              nominal one), so its S = 1 is final without the envelope. J, Hz and U (kill_frames) on the nominal lane.
  stage 2     the envelope (bounds_lo lanes' hull, Planner._contacts) in chunks of `chunk` rows, in this order: the
              core rows that passed stage 1 (always, whatever the deadline: §4.4 item 2), CONTINUE, the K_b best of
              the rest by (Hz, Hz_soft, U, -J) and up to `sibs` rows sharing each of the 8 best rows' first piece (V
              needs two safe ways on with the same first piece), then the rest in that order. After the priority
              part it stops at the first chunk that leaves a safe row; inside it, once a safe row exists and the next
              chunk would end past deadline_ms (taken to cost what the last one did). Without a safe row it goes on
              to the end (a slow tick, counted: `overrun`, never FORCED_RISK by itself: §4.4 item 3).
  hit effects within each chunk, rows with a predicted nail hit (Reaper shapes; the first hit on any enemy in reach,
              scored or not) are rolled out again with its effect (side / wall slash: recoil away, up slash: recoil
              down, down slash: bounce) and checked again: S = miss branch | hit branch (DESIGN 3.5.6). The hit branch
              also meets the hit enemy's reaction (hero_caused.json TOOK DAMAGE exits of every state its walk allows at
              the hit: a Clapper's Idle -> Dmg Attack, a Reed's Alert -> Stab Pos, a Minister's Chase -> Range Check,
              a Maestro's Fly -> Summon?, an Envoy's Charge -> Reset, ...): MultiForecaster.forecast_reaction from the
              hit frame, anchored there. At most hitfx_k rows a tick get the hit branch and react_k reaction
              forecasts; a row with a predicted hit beyond those caps is S = 1 while a safe row exists; without one,
              the capped rows get their hit branch uncapped before FORCED_RISK (the caps follow the queue's J order,
              so the prefs: FORCED_RISK must not depend on them, §4.4 item 2).
  selection   only rows whose S is known: enveloped, or in contact at stage 1. The chosen plan with S = 0 is always an
              enveloped one (audit: `audit`). FORCED_RISK: no enveloped row is safe after all were checked; the p_k
              latest first contacts (estimates: stage 1's lower bound, the envelope's first frame, the hit branch's)
              are then put on one lane over one frame set (stage 1's: the nominal box against the support, or'ed with
              the hit branch's contact, from the hit frame on where a cap left it unchecked) and ranked by the share
              of those frames in contact (P's stand-in: MultiForecast.prob costs 3.7 ms p50 on wave 6, one query per enemy, placement
              kind and probability value; exact_p turns it back on), with commit_rank (default; SSBOT_FORUM_PC=0:
              off) the share in contact with the committed support and then with the current attacks' fine placements
              (P_cm, P_f: the support's P ties at 1 in wave 0, forum.md 20.7 / 20.8; they also lead the preselection;
              stage 1's own support query split by part gives them, MultiForecast.occupied_split, forum.md 20.11),
              the latest first contact, the envelope's, J.
              forced_rank "seen" (forum.md §19) puts a key before that share, in the preselection too: the frames
              each row's nominal box meets the damage colliders seen now, moved along their entity's velocity
              (seen_contacts; fewest first, then the latest first contact). In wave 0 the support saturates (every
              row in it on every frame) and the share ties: the pick then fell to J. "seen_cf" adds, after it, the
              share of stage 1's frames in the committed fine placements (committed_fine_share: an attack under way
              whose entry is known to a few bins, its strike at its anchor; the windows and the start-later boxes,
              which saturate, are left out): the strikes that open after their antic, which "seen" cannot see yet.
              The keys stack (the integration of the wave-0 forensics and R5 value tracks): seen > committed fine
              share (seen_cf) > P > P_cm > P_f (commit_rank) > the first contacts > J; each switch off leaves its keys
              all 0 (the order of the others unchanged).
  determinism deadline_ms = inf: decisions do not depend on the machine's speed (audits, identity checks).
  unmodelled  a row that presses attack while dashing / sprinting is vetoed (the Reaper's dash stab is R7's).
  not here    the lock check past the horizon (no Silkspear in the Forum set; the Bind macro checks its own), the key
              economy terms, the killing blow's branches (so no certified final kill: I3 only), the comfort query (no
              comfort templates in the multi path).
  U / I3      the killing blow is the one that may end the battle (forum_kill_hp: the final wave's last members),
              FilterContext.kill_hp from it; not certified in R3 (no kill branches): such a blow passes only under I3.
Scores only (GoalPrefs: hit_w per enemy iid, stance, the risk map): no prefs field reaches stage 1's S, Hz, U or the
core rows' envelope, so the core rows' S / Hz / U are the same under any prefs (tests/test_forum_planner.py).
Track A of the Forum push 2 (SSBOT_FORUM_TA, TA_TOKENS below; forum.md §26; every token off by default): GoalPrefs
.hit_kw weighs a target's hits by the slash kind (side / up / wall / down); "whip" lowers J of a clash-safe row whose
clash meets a Choristor whip (it stays safe); "under" adds the under-flier bonus; "eml" prices the stage-1 contact in J
and puts the effective mask loss (masks x P - hits landed / 4) after FORCED_RISK's first-contact keys; "kb" moves the hit
enemy's support (and its reaction) by its measured knockback in the hit branch; "free" is the supervisor's (the clash
gate and I3 follow FilterContext.free).
"""
import math
import os
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numba
import numpy as np

from ssbot.combat import candidates as cmod
from ssbot.combat import dslash, forum_v2, rune_bombs, special_mode, specials, stance_block
from ssbot.combat.holdfilter import hold_filter_jit
from ssbot.combat.planner import (KillPlan, MACRO_MARGIN, NO_CONTROL_MODES, PlannerConfig, PlanResult, Planner,
                                  _hull_points, _is_macro, _rect_meets_polys)
from ssbot.combat.safety_filter import (R_KILL, REASONS, FilterContext, hazard_flags, i3_kill_allowed, kill_frames,
                                        kill_window_frames, unpausable, veto)
from ssbot.combat.terminal import EnemyFields, TerminalValue, end_class
from ssbot.core.forum import FORUM_TYPES, FORUM_WAVES, WALL_L, WALL_R
from ssbot.knowledge import kinematics as kin
from ssbot.knowledge.attack_shapes import AttackTable
from ssbot.knowledge.knockback import knockback_hull
from ssbot.knowledge.kinematics import (B_ATTACK, B_DASH, B_DOWN, B_JUMP, B_QUICKCAST, B_UP, F_ATTACKING, F_GROUND, F_INVULN,
                                        M_DASH, M_NORMAL, M_RPR_DS, M_SPRINT, HeroParams, HoldState, Terrain2D)
from ssbot.safety.supervisor import DELTA_B_S, GREEN, T_BIND_S, YELLOW

R_UNMOD = 6                       # veto reason: presses a move the model does not have (the dash stab)
ESC_LOCK_MODES = NO_CONTROL_MODES + (kin.M_RPR_DS, kin.M_DS_ANTIC, kin.M_DS_SPIKE, kin.M_HARD_LAND)
ESC_MAX_F = 72                    # escape rollouts at most this long (frames)
ESC_CHUNK = 4                     # safe rows per escape check batch
ESC_NEAR_U = 9.0                  # an attack is looked at when its reach over the check + this (the hero's travel over a
#                                   plan, the enemy's dead reckoning) is past the hero
ESC_COUNTERS = frozenset({"RE_DEFEND", "MI_PARRY"})   # guard stances: their strike is the counter to a hit
WHIP_FAMS = frozenset({("Song Pilgrim 03", "CH_WHIP")})   # the Choristor's whip (forum.md §26)
REASONS_FORUM = dict(REASONS) | {R_UNMOD: "unmodelled move (attack while dashing)"}
SLOTS = ("normal", "up", "wall", "down")   # kernel slot order (_SHAPE_*)
K_SIDE, K_UP, K_WALL, K_DOWN = 1, 2, 3, 4  # first_kind codes
WALL_TOUCH_U = 0.15               # a box edge this close to the arena wall in the air: a side slash is the wall slash
TARGET_REACH_U = 14.0             # enemies farther than this from the hero are not scored (0.6 s: dash + run ~ 8 u)
RPR_ANTIC_F, RPR_SLASH_F = 9, 11  # Reaper down slash: antic 0.150 s, slash 0.167 s (hero_reaper_forum.json)
KILL_Z = 3.0                      # hp_est - z sigma: the least HP an enemy may have (forum_planner_plan §4.2 U)
WANDERER_COMBO_F = 9              # DASHCOMBO_WINDOW_TIME 0.15 s (hero_constants.json): an attack this soon after a dash
#                                   is the Wanderer's dash combo (vetoed: not modelled)
PARRY_INVULN_F = 9                # INVUL_TIME_PARRY 0.15 s: parryInvulnTimer, set on the clash frame and decremented by
#                                   deltaTime in Update, is > 0 on that frame and the 8 after: no enemy damage there
PARRY_RECOVER_F = 6               # NailParryRecover 0.1 s after the clash: attack cooldown 0, the swing cancelled
CLASH_FILE = "clash.json"
# the aimed pins (ForumConfig.pin_aim, "+a"; forum.md §23.7, 115 pins of the round-2 runs): a Reed's pin flies on the
# frame it enters Throw, from about 1.6 u off it at 31 u/s, aimed at where the hero was about 20 frames before
# (angle p50 5 deg, p90 18 deg, max 55 deg)
PIN_THROWS = frozenset({("Song Reed", "RE_THROW")})
PIN_RELEASE = "Throw"
PIN_AIM_F = 20
PIN_SPREAD = tuple(math.radians(a) for a in (-15.0, 0.0, 15.0))
PIN_SPAWN_U = 1.6
PIN_SPEED = 31.0
PIN_HALF_U = 1.0                  # the pin's box is about 2.0 x 0.1, along its flight
PIN_SKIN = 0.15
# The Forum attacks whose Control FSM catches PARRIED, by the Control state the clash meets (forum.md 9 / 17.5: Envoy
# Charge / Reset -> Deflect -> Charge End 0.42 s; Reed Parry Slash -> Multihit Clashed 0.39 s -> Parry Slash End
# 0.33 s; the R1 v2 recordings: 171 Envoy clashes all in Charge, 24 Reed counter clashes all in Parry Slash): a clash
# there ends the attack, so the success branch holds that enemy's support where it was at the clash frame
# (PARRY_STOP_F frames: Charge End -> Attack Wait -> Walker can start a new attack at once, whose first hit comes 0.41 s
# or more later (strikes.json p5 of the jump slash); the Reed goes on to Alert, 0.72 s, then 0.65 s or more to a stab's
# first hit), the hero's hull grown by what the enemy still moves after a clash (PARRY_STOP_GROW: x, y in u at 3-frame
# steps of game time from the clash, each step the measured maximum at its end; the R1 v2 Envoy campaign runs, 55 Envoy
# charges and 21 Reed counters that ended in a clash: the Envoy slides on in Charge End up to 0.93 u, the Reed drifts up
# to 0.96 u and then flies off; forum.md 17), instead of the rest of the attack
PARRY_STOPS = frozenset({("Song Pilgrim 01", "Charge"), ("Song Pilgrim 01", "Reset"), ("Song Reed", "Parry Slash")})
PARRY_STOP_F = 48
PARRY_STOP_GROW = {"Song Pilgrim 01": ((0.372, 0.6, 0.701, 0.802, 0.847, 0.892, 0.912, 0.932), (0.01,)),
                   "Song Reed": ((0.36, 0.6, 0.96), (0.312, 0.624, 0.832, 0.832, 0.832, 0.832, 0.832, 0.832, 1.222,
                                                     2.392, 3.172, 3.952))}


def stop_grow(tk_name: str, d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """PARRY_STOP_GROW (x, y) d frames after the clash (d >= 0: the step that ends after d)."""
    gx, gy = PARRY_STOP_GROW[tk_name]
    return (np.asarray(gx)[np.minimum(d // 3, len(gx) - 1)], np.asarray(gy)[np.minimum(d // 3, len(gy) - 1)])


def clash_mix(w: float, share_branch: float, share_plain: float) -> float:
    """FORCED_RISK's share in contact of a row with a clash branch: w (every clash in it happens) x the branch's +
    (1 - w) x the plain row's (a clash that does not happen leaves the plain row: its contact, the hit included)."""
    return w * share_branch + (1.0 - w) * share_plain


H_W = {1: 1.0, 2: 1.0, 3: 0.6}     # H_exp's weight by h (hits to death; 4 and more: H_W_FAR, unknown: H_W_NONE)
H_W_FAR, H_W_NONE = 0.3, 0.5


M_GLIDE = kin.MODE_NAMES.index("GLIDE")
TV_ON = os.environ.get("SSBOT_FORUM_TV", "0") == "1"        # 1: the terminal value (off by default: forum.md 20.11)
PC_ON = os.environ.get("SSBOT_FORUM_PC", "1") != "0"        # 0: FORCED_RISK without the committed support's shares
T_ENV = int(os.environ.get("SSBOT_FORUM_T", "36") or 36)     # the horizon arm (§4.5: T 36 / 48)
# Track A of the Forum push 2 (2026-10-08, the person's decisions and tactics; forum.md §26): each behind a token of
# SSBOT_FORUM_TA ("+" or "," separated; "all": every one; empty, the default: none, everything as before):
#   free   DESIGN 3.5.6 revision: the supervisor's free mode (h >= 2: anything goes until hit; Q1 at h = 1 unchanged)
#   whip   a clash row whose clash meets a Choristor whip is still safe but scores no gain (J); L2: in its whip antic
#          leave the whip's reach (it does reach 4.75 u behind: Whip Hit 5-6) or switch to a target out of it
#   guard  L2: the Minister / Reed defence rules (height bands, wait in reach, triggers only from where its counter
#          cannot reach; the Reed never from above / below)
#   edge   RUSH's stance at the edge of the hero's slash reach on the target's body (not its x)
#   under  J: the under-flier bonus (below.json: the attack-weighted hit rate in front less below, per flyer type)
#   eml    J and FORCED_RISK's tie-break after the preselection keys: the effective mask loss (P x masks - hits / 4)
#   kb     the hit branch moves the hit enemy (its support and its reaction) by its measured knockback
TA_TOKENS = ("free", "whip", "guard", "edge", "under", "eml", "kb")


def parse_ta(spec: str | None) -> frozenset:
    """SSBOT_FORUM_TA's tokens (TA_TOKENS); "all" = every one; unknown tokens raise."""
    toks = {t.strip().lower() for t in str(spec or "").replace(",", "+").split("+") if t.strip()}
    if "all" in toks:
        return frozenset(TA_TOKENS)
    bad = toks - set(TA_TOKENS)
    if bad:
        raise ValueError(f"SSBOT_FORUM_TA={spec!r}: unknown {sorted(bad)} (tokens {TA_TOKENS} or all)")
    return frozenset(toks)


TA_ENV = os.environ.get("SSBOT_FORUM_TA", "")
# SSBOT_FORUM_CL_NODOWN=1 (the person, 2026-10-12, watching the live demos: after the rune hop the planner kept
# choosing down slashes, so the hero was airborne when the slam antic began and could not reach the strike spot):
# with a Clapper within CL_NODOWN_U of the hero, no row of the posture set presses a down slash; the special rows'
# strike is kept (stand in front of it, ready for the special)
CL_NODOWN = os.environ.get("SSBOT_FORUM_CL_NODOWN", "0").strip() == "1"
CL_NODOWN_U = 12.0
# SSBOT_FORUM_SPECIAL_MAP=1 (task 1v1 SG4, forum.md 59): the Clapper slam's score map in the planner (combat.forum_map):
# the map row during a tracked CL_SLAM (judged as a special row, first among the safe rows), the readiness penalty
# before a slam can start (replaces SSBOT_FORUM_CL_NODOWN, which is then ignored), the L2 spots. Off: no change.
SPECIAL_MAP = os.environ.get("SSBOT_FORUM_SPECIAL_MAP", "0").strip() == "1"
# SSBOT_FORUM_CHASE=1 (task 1v1 SG5, forum.md 61; needs SSBOT_FORUM_SPECIAL_MAP=1): chase and slash outside the slam:
# per tick the chase rows (run / dash toward a Clapper that idles, walks, evades or enters, then a slash every 19
# frames with the side key held a few frames after each press to follow the knockback; every check stays), and the
# map's readiness of a row's end as a tier above the landed hits (the rows below R_ref after the others) where SG4's
# soft penalty traded readiness for hits; L2's chase stance (tactics.gauntlet). Off: no change.
CHASE = SPECIAL_MAP and os.environ.get("SSBOT_FORUM_CHASE", "0").strip() == "1"
# SSBOT_FORUM_SG8=1 (task 1v1 SG8, forum.md 64; needs SSBOT_FORUM_SPECIAL_MAP=1): the fixes from the first live runs
# (combat.forum_map: the airborne locate, the lunge re-anchored, the map's fallback near the face; here the slam's
# FORCED_RISK keys and the off-lattice rows ranked after a safe map row; the small runes' hop tier). Off: no change.
SG8 = SPECIAL_MAP and os.environ.get("SSBOT_FORUM_SG8", "0").strip() == "1"
CHASE_TIER = 300.0            # the readiness tier (landed-hit units: above any hit count, below the corner's 1000)
CHASE_TIER_U = 6.5            # ... for the rows ending this close to the Clapper (centre to centre, u): in slash reach
#                               the end state must leave R_ref (SG4: readiness >= WC + 2 at the antic entry, 2.00 strikes,
#                               0.09 % damaged starts; (WC, WC + 1) 0.19 %); farther out SG4's soft penalty as before
#                               (a tier there would rank a retreat past 12 u (R <= WC) over an approach still 7 u out)
CHASE_RUN_K = (0, 4, 8, 12, 16, 20, 24)   # the run rows' first press frame (the side key held until it)
CHASE_DASH_K = (10, 14, 18, 22)           # the dash rows' (a press while the dash runs is the dash stab: candidates.DASH_WAIT)
CHASE_FOLLOW = (4, 8)         # frames the side key is held from each press: a landed slash knocks it back ~0.48 u and
#                               the hero ~0.5 u (recoil 3.75 u/s x 8 steps); run 8.25 u/s = 0.1375 u per frame
CHASE_PERIOD = 19             # frames between presses (Wanderer attack_cooldown 0.3 s = 18 frames)
CHASE_AIM_U = 4.3             # the run rows' first press: where a run (CHASE_RUN_UF u per frame) reaches this distance,
CHASE_RUN_UF = 0.1375         # the press frames within CHASE_K_TOL of it (the deadline replays: 22 rows on every tick
CHASE_K_TOL = 8               # cut the escape check on +19 % ticks)
CHASE_DASH_U = 6.5            # the dash rows only from farther than this (a dash covers ~2.8 u)
CHASE_NEAR_U = 14.0           # a Clapper this close (x) gets chase rows
CHASE_FAMS = (None, "CC_EVADE", "CC_ENTRY")   # its instance then (idle / walk: none)
CHASE_RUNE_S = 1.1            # no chase rows this long after a jump cast (its rune circle bursts 0.75-0.87 s after it)


def _hold_pad(row, T: int) -> np.ndarray:
    """M4d2: the held bridge as a CONTINUE row of T frames (padded like candidates.continue_plan: its last frame's
    movement keys)."""
    r = np.asarray(row, np.int64).reshape(-1)
    out = np.zeros(T, np.int64)
    k = min(len(r), T)
    out[:k] = r[:k]
    if k < T:
        out[k:] = (int(r[-1]) if len(r) else 0) & (kin.B_LEFT | kin.B_RIGHT)
    return out


def chase_tier_low(R: np.ndarray, safe: np.ndarray, xe: np.ndarray, cx: float | None, ref: float,
                   near_u: float = CHASE_TIER_U) -> np.ndarray:
    """SSBOT_FORUM_CHASE (SG5): [N] the rows the readiness tier puts after the others: safe, ending within near_u of
    the Clapper (centre to centre, the readiness's Clapper x) with the map's readiness of the end state below ref (nan:
    not computed, never low; -inf: no safe continuation, low)."""
    if cx is None:
        return np.zeros(len(R), bool)
    Rf = np.where(np.isnan(R), np.inf, R)
    return np.asarray(safe, bool) & (np.abs(np.asarray(xe) - float(cx)) <= near_u) & (Rf < ref)


# review (SG4): the map row's planner lane (hold-filtered keys, the map's bounces) may leave the map's own path by at
# most one run step in x (0.165 u: a stretched one-frame tap, the map's x dilation is 0.2475 u) and the map's y dilation
MAP_LANE_TOL_X = 0.2
MAP_LANE_TOL_Y = 0.12
# review (SG4): the map's own work (the map row, its special context, the readiness) does not count against the
# envelope / escape / clash deadlines (with deadlines on, replays: the escape check ran out of time on +63 % ticks and
# the chosen rows were left unchecked); SSBOT_FORUM_SPECIAL_MAP_DL=0: they count (SG4)
MAP_DL_SHIFT = os.environ.get("SSBOT_FORUM_SPECIAL_MAP_DL", "1").strip() != "0"
# task oldwin (with SSBOT_FORUM_WINDOWS): SSBOT_FORUM_WINDOWS_MEASURE=1 was d13788fa's offline measurement of the planner's
# own contact on the window rows; since stage F that contact is always computed (it decides a row's certainty) - unused
WIN_MEASURE = os.environ.get("SSBOT_FORUM_WINDOWS_MEASURE", "0").strip() == "1"
# stage F: SSBOT_FORUM_WINDOWS_PLC (default 1) - a window row is a certain hit only when the planner's own strike model
# meets its target on the table's contact frame (else judged on its own lane); 0: every in-horizon row certain (d13788fa)
WIN_PLC = os.environ.get("SSBOT_FORUM_WINDOWS_PLC", "1").strip() != "0"
# stage F: SSBOT_FORUM_WINDOWS_CORE=1 enveloped as core rows (never cut by the deadline) with their hit enemy's reaction
# under the old cap (d13788fa); default 0: after the old planner's own rows, cut by the deadline, their reaction checked
# outside the cap without spending it (h2's rows keep their order, time and reaction budget)
WIN_CORE = os.environ.get("SSBOT_FORUM_WINDOWS_CORE", "0").strip() in ("1", "2")
# stage N: SSBOT_FORUM_WINDOWS_CORE=2 - enveloped as core rows (never cut by the deadline: stage L's live 0 / 984) with
# their hit enemy's reaction checked OUTSIDE the cap without spending it (stage F's fix for the cap starving them); =1:
# d13788fa's core order under the cap
WIN_CORE_CAP = os.environ.get("SSBOT_FORUM_WINDOWS_CORE", "0").strip() == "1"
# stage N: SSBOT_FORUM_WINDOWS_RANK=1 (default 0) - a safe CERTAIN window row (the two models agree on its contact, or
# its credited strike past the horizon) ranks first among the safe rows with the same keys above the landed hits (below
# every safety / commitment key: hz, U, S, clash, keep, the kept / held rows, NODASH & co.): ahead of v2_nh / v2_ff
WIN_RANK = os.environ.get("SSBOT_FORUM_WINDOWS_RANK", "0").strip() == "1"
WAITS_ON = os.environ.get("SSBOT_FORUM_WAITS", "0") == "1"   # 1: the timing rows (candidates.build_forum waits)


@dataclass
class ForumConfig:
    T: int = T_ENV                # 0.6 s (§4.5); SSBOT_FORUM_T=48: the R5 horizon arm
    variants: str = "bounds_lo"
    chunk: int = 32
    K_b: int = 96
    sibs: int = 3
    deadline_ms: float = 8.0      # the envelope stops before a chunk that would end past it (once the core rows
    #                               are done and a safe row exists; forum.md 15.11: 11 ms put the tick p99 above the
    #                               Bell Beast's); inf: deterministic decisions (the only timing-dependent rule)
    hitfx_k: int = 32
    react_k: int = 4
    K_tgt: int = 4
    p_k: int = 16
    exact_p: bool = False         # FORCED_RISK ranks by MultiForecast.prob (3.7 ms p50 on wave 6: one query per enemy,
    #                               placement kind and probability value) instead of the share of frames in contact
    p_all: bool = False           # audits (tools/forum_tv_audit): FORCED_RISK's P / first contact for every allowed
    #                               known row, the choice still among the p_k preselected (decisions unchanged)
    forced_rank: str = "share"    # FORCED_RISK's first risk key: "share" (the support share, above), "seen" (frames in
    #                               contact with the damage colliders seen now, moved along their entity's velocity,
    #                               then the share; forum.md §19: the support saturates in wave 0 and the share ties),
    #                               "seen_cf" (seen, then the share of frames in the committed attacks' fine
    #                               placements: the strikes of attacks already under way whose entry is known)
    commit_rank: bool = PC_ON     # FORCED_RISK: rows tied on P ranked by their share of stage 1's frames in contact
    #                               with the committed support (P_cm: current attacks, tails, death tails, hazards),
    #                               then with the current attacks' fine placements (P_f) (forum.md 20.7: P ties at 1 in
    #                               wave 0); they lead the preselection too; scores only (S, Hz, U unchanged); on by
    #                               default since the round-2 A/B (forum.md 20.8: hits / min 18.9 -> 12.4); the
    #                               parts come from stage 1's own query (MultiForecast.occupied_split, forum.md 20.11)
    terminal: bool = TV_ON        # the terminal value (R5, combat.terminal): E / trapped / overlap / H_exp into J, the
    #                               kill value into the target weights; scores only; off by default (SSBOT_FORUM_TV=1:
    #                               on): no closed-loop gain in wave 0 (forum.md 20.5: 18.4 hits / min with and
    #                               without) and it runs before the envelope, inside its deadline (0.9-1.3 ms p50)
    w_E: float = 4.0              # J per unit of E (the reachable share clear of the enemies' bodies, 0..1)
    w_trap: float = 3.0           # J off when every way out closes within TRAP_S
    w_ov: float = 1.5             # J off per unit of overlap (reachable share inside two enemies' zones)
    w_H: float = 2.0              # J off per unit of H_exp (reachable share inside a 2-mask / multi-hit enemy's zone),
    #                               times H_W[h]
    w_K: float = 3.0              # a target's hit weight x (1 + w_K kill value)
    react: str = "off"            # reactive support (forum.md §22): "off"; "delay" (MultiForecaster.react: an attack
    #                               that has not started strikes no earlier than its wind-up); "escape" (delay and the
    #                               escape check: the chosen safe plan leaves the hero able to get out of the reach of
    #                               any attack an enemy may start at its end or at a late lock-in); "+c" / "+i" / "+p5"
    #                               extensions (multi_forecast.ReactConfig)
    esc_k: int = 4                # safe rows (in the order) the escape check looks at for one that passes
    esc_k_forced: int = 8         # FORCED_RISK: the first rows of the order it looks at (those tied above the share)
    esc_deadline_ms: float | None = None   # the escape check starts no batch that would end past this many ms from
    #                                         the tick's start (a batch costs about what the last ones did; none run:
    #                                         the order's choice); None: deadline_ms + 2 (inf: deterministic)
    esc_after_f: int = 18         # frames past an attack's first damage its escape path must stay out of it
    # EV_CLASH (forum_planner_plan R8; off: the R3 / R4 planner bit for bit): when no row is safe, rows in contact whose
    # swing is out at the first contact get the clash branch (success: 0.15 s i-frames against all enemy damage, the
    # direction's recoil, the attack reset 0.1 s later; failure: the hit); its weight w is the probability that every
    # clash in it happens (the product of clash.json's p_clash_lb by type x family x slot, in the family's clashable
    # states): a clean branch counts as safe when w >= clash_min_p and its hit probability (1 - prod(1 - p_fail)) is at
    # most clash_max_fail; any other branch with w >= clash_partial_min_p enters FORCED_RISK's ranking with the share
    # w x the branch's + (1 - w) x the share without (a clash that does not happen leaves the plain row)
    clash: bool = False
    clash_branch: bool = True     # False: the clash continuations only (candidates.build_forum(clash=True); the A/B's
    #                               control for the extra rows)
    waits: bool = WAITS_ON        # the timing rows: a jump / dash after a 3-12 frame wait, a press at a guard's counter
    #                               (candidates.build_forum waits; SSBOT_FORUM_WAITS=1; off by default)
    clash_tiers: tuple = ("GREEN",)   # DESIGN 3.5.6: no parry / clash in YELLOW / RED or PAUSE_PENDING (the clash
    #                                   freeze swallows a pause); ("GREEN", "YELLOW"): the R8 experiment (lead's call)
    clash_k: int = 8              # rows a tick get the clash branch
    clash_min_p: float = 0.75
    clash_max_fail: float = 0.25
    clash_partial_min_p: float = 0.25
    clash_min_h: int = 2          # masks the hero must have (a failed clash costs 1-2)
    clash_depth: int = 2          # clashes chained in one row (multi-segment attacks, the two-sided rule)
    clash_deadline_ms: float | None = None   # the clash pass starts no level that would end past this many ms from the
    #                                           tick's start (it costs about what its last level did); None:
    #                                           deadline_ms + 2 (inf: deterministic)
    clash_main: bool = False      # the three-layer support (forum.md §23; combat_run --forum-clash main): the clash pass
    #                               runs in GREEN and in a YELLOW with h >= clash_main_h (a YELLOW from the last plan's
    #                               S = 1, not from h 2), a clean branch whose hit-anyway bound (1 - prod(1 - p_fail)) is
    #                               at most clash_max_fail is safe whatever w (the clash geometry: the swing's active
    #                               window holds the first contact, on the slash's side, in a clashable state), and the
    #                               clash-safe rows rank after the plain safe ones by that bound (clash_p)
    clash_main_h: int = 3
    bell_hits: bool = True        # bells in reach are hit targets (weight 0): a row whose first hit is a bell before
    #                               its contact gets the hit branch with that bell knocked back (the hit-back bells,
    #                               forum.md bell paragraph / §23: no hazard to the hero from the hit on)
    ta: str = TA_ENV              # track A's tokens (TA_TOKENS, SSBOT_FORUM_TA; empty: none)
    w_whip_clash: float = 1.0     # "whip": J off a clash-safe row whose clash meets a whip, in hit weights (the row's
    #                               own hits on that Choristor are taken off too: no gain)
    w_under: float = 10.0         # "under": J per unit of the hit-rate gain x the share of frames under a flyer
    under_dx_u: float = 0.6       # ... under = the box centre within the flyer's body half-width + this (x)
    eml_mask: float = 1.154       # "eml": masks a contact costs (forum.md 24.3: 1,876 masks in 1,626 hits)
    eml_hits_per_mask: float = 4.0   # the person's exchange: 4 hits landed = 1 mask (9 silk heal 3)
    kb_scale: float = 1.0         # "kb": the measured knockback's factor (medians, forum.md §26)
    # v2-lite (combat.forum_v2, SSBOT_FORUM_V2=1; forum.md §43): with a V2Forecast the safe test reads the attack-range
    # estimate + margin, the pending aims' zones, the hit branch's counters from the estimate's templates; every chosen
    # row needs an escape from its end; safe rows rank by landed hits (then the first hit's frame) before J; the timing
    # rows are in the set (the extension search: they are enveloped only when the prioritised rows leave none safe);
    # no clash pass. Off: the planner bit for bit.
    v2: bool = forum_v2.V2_ON
    v2_esc_k: int = 16            # v2: safe rows (in the order) the escape check may look at for one with an escape

    @property
    def tac(self) -> frozenset:
        return parse_ta(self.ta)

    @property
    def escape(self) -> bool:
        return self.react.strip().lower().split("+")[0] == "escape"

    @property
    def notstarted(self) -> bool:
        """The reactive support's "+n" (multi_forecast.ReactConfig.notstarted): attacks not started are out of the
        support, so the escape check looks at every lock-in of a plan, not only the late ones."""
        return "n" in self.react.strip().lower().split("+")[1:]

    @property
    def pin_aim(self) -> bool:
        """"+a": a Reed's pin not thrown yet is checked per row, aimed at where that row puts the hero PIN_AIM_F
        frames before each possible release (ForumPlanner._pin_contacts, forum.md §23.7). On with "+n" too (forum.md
        §23.12): "+n" takes the Reed's throw out of the support (its body and the pin's path once it flies), so the
        aimed check is the only layer that sees a throw whose wind-up has started (the review of 2026-10-08)."""
        toks = self.react.strip().lower().split("+")[1:]
        return "a" in toks or "n" in toks

    @property
    def esc_veto(self) -> bool:
        """With "+n" and the escape check (forum.md §23.12): the attacks not started are only the escape check's, so a
        chosen row it failed, or could not check in time, is not safe (S = 1: YELLOW, never certified), not a ranking
        preference over a plan still called safe."""
        return self.escape and self.notstarted

    @property
    def body_reach(self) -> tuple[bool, bool]:
        """"+b" / "+br" (with "+n"; multi_forecast.ReactConfig.bodyreach): the body-only families not started are out
        of the support (but BODYREACH_KEEP's types with "+b"), so the escape check takes them as threats (no wind-up:
        from the check point on). (on, every type)."""
        toks = self.react.strip().lower().split("+")[1:]
        return ("b" in toks or "br" in toks) and "n" in toks, "br" in toks

    @property
    def lock_check(self) -> bool:
        """"+k" (escape only; task forum push 2 track B, forum.md 24.5 item 4): a dash or a sprint entered is a lock-in
        the escape check looks at like an attack pressed or a mode without control; the Bind macro is not taken while
        an attack the escape check holds (one not started, "+n") may start and reach the hero in the Bind's lock
        (ForumPlanner._bind_threatened)."""
        return self.escape and "k" in self.react.strip().lower().split("+")[1:]

    @property
    def seen_sweep(self) -> bool:
        """"+s" (task forum push 2 track B, the Reed's pins): FORCED_RISK's seen key tests a fast polygon (a flying
        pin) a frame early and late too (seen_contacts_swept), and counts a row that meets an aimed pin not thrown yet
        (pin_aim) as a seen contact: the pin hits all came in FORCED_RISK, where the aimed check's S = 1 changes
        nothing and the seen key let rows graze the pin's predicted tip (forum.md 24.3)."""
        return "s" in self.react.strip().lower().split("+")[1:]

    @property
    def light_cone(self) -> bool:
        """"+l" (escape only): the escape check also asks that the plan's end has a way out of the committed
        must-escape placements with a known timing past the horizon (ForumPlanner._light_cone_occ, forum.md §23)."""
        return self.escape and "l" in self.react.strip().lower().split("+")[1:]


@dataclass
class EnvelopeAudit:
    """Per planner: ticks, chosen plans with S = 0 and of them enveloped (must be equal), FORCED_RISK ticks and of
    them the chosen plan enveloped / known in contact at stage 1, ticks past the deadline without a safe row
    (overrun), rows enveloped, hit branches, reaction forecasts, rows set S = 1 by a cap."""
    ticks: int = 0
    chosen_safe: int = 0
    chosen_safe_enveloped: int = 0
    forced: int = 0
    forced_enveloped: int = 0
    forced_stage1: int = 0
    overrun: int = 0
    deadline_cut: int = 0
    rows_enveloped: int = 0
    rows_stage1: int = 0
    hit_branches: int = 0
    reactions: int = 0
    capped: int = 0
    uncapped_ticks: int = 0       # ticks without a safe row whose capped rows got their hit branch uncapped
    uncapped_rows: int = 0
    core_not_enveloped: int = 0   # core rows past stage 1 left without the envelope (must stay 0)
    esc_ticks: int = 0            # ticks with a safe row and threats the escape check looked at ("escape")
    esc_pass: int = 0             # ... whose chosen row passed it
    esc_rows: int = 0             # rows it checked
    esc_forced_ticks: int = 0     # FORCED_RISK ticks the escape check ranked (rows tied above the share)
    esc_forced_pass: int = 0      # ... whose chosen row passed it
    esc_forced_moved: int = 0     # ... whose chosen row is not the order's first
    esc_cut: int = 0              # ticks the escape check stopped before a batch at esc_deadline_ms
    clash_ticks: int = 0          # ticks the clash branch ran (no safe row, clash on)
    clash_tier_skip: int = 0      # ... skipped: the tier is not in clash_tiers, or a pause is pending
    clash_cut: int = 0            # ... stopped before a level by clash_deadline_ms
    clash_rows: int = 0           # rows it made safe
    clash_chosen: int = 0         # chosen plans that rely on a clash
    clash_cand: int = 0           # rows the branch looked at (in contact, a swing, latest contact first, capped)
    clash_inwin: int = 0          # ... whose first contact fell in a swing's active window (per clash level)
    clash_owned: int = 0          # ... in contact there with an enemy in an attack of its own
    clash_off_state: int = 0      # ... with an owner in a clashable family outside its clashable states there
    clash_known: int = 0          # ... one of them clashable with that slot on the slash's side, in its clashable states
    clash_coowned: int = 0        # ... with a committed co-owner that cannot be clashed there (covered by the i-frames)
    clash_stops: int = 0          # ... of which an attack the clash ends (PARRY_STOPS)
    clash_partial: int = 0        # rows in FORCED_RISK's ranking with their branch's share (partial, or w below min_p)
    clash_partial_chosen: int = 0 # chosen FORCED_RISK plans that are such rows
    clash_ms: float = 0.0         # time in the clash branch
    pin_ticks: int = 0            # ticks with an aimed-pin threat (pin_aim)
    pin_rows: int = 0             # ... rows it set S = 1
    esc_unsafe: int = 0           # ticks with a safe row whose chosen row is S = 1 by the escape check (esc_veto):
    esc_failed: int = 0           # ... it failed the check (every checked row failed: the fewest failures chosen)
    esc_unchecked: int = 0        # ... no row checked before esc_deadline_ms with threats in reach
    esc_carried: int = 0          # ... a carried CONTINUE of such a row
    stance_rows: int = 0          # hit-branch rows whose first hit is a tink on a guard stance (stance_block): unsafe
    whip_clash_rows: int = 0      # clash-safe rows whose clash meets a Choristor whip, J lowered (track A "whip")
    kb_rows: int = 0              # hit-branch rows whose hit enemy was moved by its knockback (track A "kb")
    bind_threat: int = 0          # Bind macros the support passed and "+k"'s lock check refused (_bind_threatened)
    v2_aim_rows: int = 0          # v2: rows a pending aim's zone set S = 1
    v2_react: int = 0             # v2: hit-branch counters placed from the estimate's templates
    v2_esc_rows: int = 0          # v2: rows the escape check (from the row's end) looked at
    v2_dash_rows: int = 0         # v2 focus margin: rows dashing at the focus unit (read with its "rule" margin)
    v2_dash_unsafe: int = 0       # ... of them in contact only with that margin
    v2_esc_more: int = 0          # v2: rows the escape check looked at past the first v2_esc_k (forum_v2.ESC_MORE)
    v2_esc_tail: int = 0          # v2: chosen rows whose passing escape became the plan's tail (forum_v2.ESC_TAIL)
    spec_ticks: int = 0           # specials (SSBOT_FORUM_SPECIALS): ticks with arrive-and-strike rows, the rows, the ones
    spec_rows: int = 0            #   safe after every check, the ticks that chose one
    spec_safe: int = 0
    spec_chosen: int = 0
    sm_ticks: int = 0             # the special mode (SSBOT_FORUM_SPECIAL_MODE, combat.special_mode): ticks with special
    sm_rows: int = 0              #   rows (a contact with E in M found), the rows, those whose keys the allowlist vetoed,
    sm_keys_veto: int = 0         #   the long ones (press past the horizon), those whose continuation is clear, the rows
    sm_long: int = 0              #   safe after every check, the ticks with one, the ticks that chose one (CONTINUE of a
    sm_tail_ok: int = 0           #   special row included), the chosen ones failing T1's real-box approach check
    sm_safe: int = 0              #   (diagnostic, not a filter), the mode's time
    sm_safe_ticks: int = 0
    sm_chosen: int = 0
    sm_appr_fail: int = 0
    sm_ms: float = 0.0
    sm_tail_esc: int = 0          # special rows whose escape is their own clear continuation
    sm_hit_credit: int = 0        # special rows credited their strike as a landed hit (the scorer had none)
    sm_appr_hammer: int = 0       # chosen special rows whose approach meets the move's attack box (T1's check)
    hop_ticks: int = 0            # SSBOT_FORUM_RUNE_HOP: ticks with the person's hop rows (task 1v1 G2)
    hop_rows: int = 0
    hop_safe: int = 0
    hop_chosen: int = 0
    noglide_ticks: int = 0        # SSBOT_FORUM_NOGLIDE: ticks with safe rows both with and without a glide
    nodash_ticks: int = 0         # SSBOT_FORUM_SLAM_PLAY_NODASH: ticks with safe rows both with and without a dash
    rx_ticks: int = 0             # SSBOT_FORUM_TWO_RUNEEXIT (SP12a): ticks with a circle still to light passed
    rx_split: int = 0             # ... of them with safe rows both late and not late for its exit
    nopogo_ticks: int = 0         # SSBOT_FORUM_SLAM_PLAY_NOPOGO: ticks with safe rows both with and without an air hit
    jb_nojump_ticks: int = 0      # SSBOT_FORUM_JB_NOJUMP: ticks with safe rows both with and without a jump key
    sm_uncert: int = 0            # review: special rows (contact found) whose press on the planner's own lane is in no
                                  #   certified entry (full checks instead)
    sm_hit_other: int = 0         # review: special rows whose first predicted hit is another enemy (hit branch run)
    sm_forced_out: int = 0        # review: FORCED_RISK ticks whose special rows were taken out of the ranking
    sg8_forced_slam: int = 0      # SSBOT_FORUM_SG8: FORCED_RISK ticks in a tracked slam (the slam keys ranked them)
    sg8_offl_rows: int = 0        # ... rows ranked after a safe map row (a dash / sprint / glide / horizontal slash)
    sg8_hop_tier: int = 0         # ... Cast 2 ticks with a safe hop row (the hop tier ranked the air dashes after it)
    hop_inflight: int = 0         # review: hop rows dropped: their press is not a jump from the ground (model)
    cl_nodown: int = 0            # SSBOT_FORUM_CL_NODOWN: down-slash rows of the set dropped near a Clapper
    map_ticks: int = 0            # SSBOT_FORUM_SPECIAL_MAP: ticks with a map row; of those safe / taken; the full
    map_safe: int = 0             #   support's cross-check flagged the map row (not a veto); ticks during a slam
    map_taken: int = 0            #   without a row; the CL_NODOWN switch ignored; ticks with a readiness penalty,
    map_xcheck: int = 0           #   of those where it changed the chosen row; rows put last (no safe continuation)
    map_off: int = 0
    map_nodown_ignored: int = 0
    chase_ticks: int = 0          # SSBOT_FORUM_CHASE (SG5): ticks with chase rows; the rows, safe ones, chosen ticks
    chase_rows: int = 0
    chase_safe: int = 0
    chase_chosen: int = 0
    chase_tier_ticks: int = 0     # ... ticks with the readiness tier; safe rows put below it; ticks it changed the first
    chase_tier_rows: int = 0
    chase_tier_changed: int = 0
    ready_ticks: int = 0
    ready_changed: int = 0
    ready_out_rows: int = 0
    map_lane_off: int = 0         # review: map rows whose planner lane left the map's path (kept the full checks)
    map_lane_contact: int = 0     #   ... whose first contact on the lane is not the map's
    v2_corner_rows: int = 0       # v2: safe rows ranked last for ending in a Clapper's corner (forum_v2.corner_zones)
    sm_full_ticks: int = 0        # SSBOT_FORUM_SPECIAL_FAST (G3): ticks that rolled the whole template set
    sm_board_cached: int = 0      #   ticks whose BOARD is the last full tick's strike spot
    win_ticks: int = 0            # task oldwin (SSBOT_FORUM_WINDOWS): ticks with window rows given to the checks
    win_rank_ticks: int = 0       # stage N (SSBOT_FORUM_WINDOWS_RANK): ticks with a safe certain window row ranked first
    win_rows: int = 0             #   the rows
    win_chosen: int = 0           #   ticks a window row was chosen (safe)
    win_forced_out: int = 0       #   stage F: FORCED_RISK ticks whose certain window rows were taken out of the ranking
    ds_ticks: int = 0             # SSBOT_FORUM_DSLASH (task 1v1 G3): ticks the family ran (a real target in reach)
    ds_tpl: int = 0               #   templates rolled out to their press
    ds_pass: int = 0              #   templates through the prefilter (the blade meets a predicted body)
    ds_rows: int = 0              #   family rows given to the checks
    ds_cert: int = 0              #   of them under the certain-hit rule (bounce branch only)
    ds_chain: int = 0             #   of them with a certain second strike
    ds_chain_tail_fail: int = 0   #   chain rows dropped: their tail past the horizon meets the support
    ds_safe: int = 0              #   family rows safe after every check
    ds_safe_ticks: int = 0        #   ticks with a safe family row
    ds_chosen: int = 0            #   ticks a safe family row was chosen
    ds_chosen_cert: int = 0
    ds_chosen_chain: int = 0
    ds_credit: int = 0            #   family rows credited a certain strike past the horizon
    ds_busy: int = 0              #   review2: ticks with a swing under way / pressed in the prefix (no certain row)
    ds_cont2: int = 0             #   review2: certain rows holding a second press, offered only as their chain twin
    ds_anchor: int = 0            #   review2: certain rows whose hit branch is anchored at the certain contact
    ds_anchor_nohit: int = 0      #   of them the scorer saw no hit on (before review2: no hit branch at all)
    ds_anchor_moved: int = 0      #   of them the scorer's first hit was another frame / target
    hf_esc_reused: int = 0        # review2: rows whose escape result at the selection is the HITS_FIRST tier's
    ds_ms: float = 0.0
    mh_targets: int = 0           # SSBOT_FORUM_MOVE_HITS (G4 5b): target bodies put on their move path (calls x targets)
    hf_ticks: int = 0             # SSBOT_FORUM_HITS_FIRST (G4 4c): ticks with strike options ordered by hits
    hf_stop: int = 0              #   ticks a strike option passed every check before the rows with fewer hits
    hf_stop2: int = 0             #   of them on a two-hit (or more) option
    hf_skipped: int = 0           #   rows not enveloped for it (fewer hits than the passing option)
    hf_skipped_strike: int = 0    #   of them strike options (one-hit special / family rows)
    kp_ticks: int = 0             # SSBOT_FORUM_SPECIAL_KEEP (G4 4b): ticks with a kept template
    kp_kept: int = 0              #   ticks it was chosen again
    kp_skip: int = 0              #   template searches skipped for it
    kp_done: int = 0              #   the kept template ran out (its press under way or none left): not a switch
    kp_sw_gone: int = 0           #   switches: the template's row is gone (contact / certified press lost, move over)
    kp_sw_unsafe: int = 0         #   switches: a check failed (S, hazards, the committed hold, the macro margin)
    kp_sw_escape: int = 0         #   switches: the escape check moved the choice off it

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def posture_of(start: np.ndarray) -> str:
    st = np.asarray(start).reshape(kin.K, -1)[:, 0]
    if st[kin.WSIDE] != 0 or st[kin.CLING] > 0:
        return "wall"
    return "ground" if st[kin.GROUND] > 0 else "air"


def _shapes(crest: str = "Reaper") -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """The kernel's attack shapes: verts for facing +1 and -1 (concatenated over SLOTS), slot starts [len(SLOTS) + 1],
    active windows [len(SLOTS), 2] (frames after the attack's start; the Reaper down slash's from its antic's start,
    a down slash of the Slash type (Wanderer) from the swing's start like the others)."""
    tab = AttackTable.load(crest)
    vs, st, win = [], [0], []
    for s in SLOTS:
        sh = tab[s]
        p = np.concatenate(sh.polys)
        vs.append(p)
        st.append(st[-1] + len(p))
        if s == "down" and tab.config.get("down") == "Custom":
            win.append((RPR_ANTIC_F, RPR_ANTIC_F + RPR_SLASH_F))
        else:
            f0, f1 = sh.frames if sh.frames else (int(round(sh.t_on * 60)), int(round(sh.t_off * 60)))
            win.append((int(f0), int(f1) + 1))
    v = np.concatenate(vs)
    vl = v.copy()
    vl[:, 0] = -vl[:, 0]
    return (np.ascontiguousarray(v), np.ascontiguousarray(vl), np.array(st, np.int64), np.array(win, np.int64))


@numba.njit(cache=True)
def _meets(tb0, tb1, tb2, tb3, verts, a, b, cx, cy):
    starts = np.empty(2, np.int64)
    starts[0], starts[1] = a, b
    return _rect_meets_polys(tb0, tb1, tb2, tb3, verts, starts, cx, cy)


@numba.njit(cache=True, parallel=True)
def seen_contacts(box, inv, verts, starts, pbox, vel, tk, rows, grow):
    """FORCED_RISK's "seen" key (ForumConfig.forced_rank): per row of `rows`, the frames 1 .. T1 - 1 its nominal box
    (grown by `grow`; invulnerable frames clear) meets a damage polygon seen now moved along its entity's velocity
    (tk[k] s on), and the first such frame (T1: none). pbox [n, 4]: each polygon's bounding box (a cheap reject).
    No forecast: what is already there and where it is going, not what may start."""
    N, T1 = box.shape[0], box.shape[1]
    n_p = len(starts) - 1
    cnt = np.zeros(N, np.int64)
    first = np.full(N, T1, np.int64)
    for m in numba.prange(len(rows)):
        c = rows[m]
        for k in range(1, T1):
            if inv[c, k]:
                continue
            x0, y0, x1, y1 = box[c, k, 0] - grow, box[c, k, 1] - grow, box[c, k, 2] + grow, box[c, k, 3] + grow
            for p in range(n_p):
                dx, dy = vel[p, 0] * tk[k], vel[p, 1] * tk[k]
                if pbox[p, 0] + dx > x1 or pbox[p, 2] + dx < x0 or pbox[p, 1] + dy > y1 or pbox[p, 3] + dy < y0:
                    continue
                if _rect_meets_polys(x0, y0, x1, y1, verts, starts[p:p + 2], dx, dy):
                    cnt[c] += 1
                    if first[c] == T1:
                        first[c] = k
                    break
    return cnt, first


# "+s" (task forum push 2 track B, the Reed's pins: forum.md 24.3, all in FORCED_RISK): a seen polygon this fast is
# tested a frame early and late as well (its timing: the export lags a frame now and then, a pin flies 0.5 u a frame;
# the chosen rows grazed the pin's predicted tip and were hit)
SEEN_SWEEP_MIN_U_S = 15.0


@numba.njit(cache=True, parallel=True)
def seen_contacts_swept(box, inv, verts, starts, pbox, vel, tk, rows, grow, lag, vmin):
    """seen_contacts with the polygons at least vmin u/s fast also tested at tk[k] - lag and tk[k] + lag."""
    N, T1 = box.shape[0], box.shape[1]
    n_p = len(starts) - 1
    cnt = np.zeros(N, np.int64)
    first = np.full(N, T1, np.int64)
    for m in numba.prange(len(rows)):
        c = rows[m]
        for k in range(1, T1):
            if inv[c, k]:
                continue
            x0, y0, x1, y1 = box[c, k, 0] - grow, box[c, k, 1] - grow, box[c, k, 2] + grow, box[c, k, 3] + grow
            hit = False
            for p in range(n_p):
                fast = vel[p, 0] * vel[p, 0] + vel[p, 1] * vel[p, 1] >= vmin * vmin
                for j in range(3):
                    if j != 1 and not fast:
                        continue
                    t = tk[k] + (j - 1) * lag
                    dx, dy = vel[p, 0] * t, vel[p, 1] * t
                    if pbox[p, 0] + dx > x1 or pbox[p, 2] + dx < x0 or pbox[p, 1] + dy > y1 or pbox[p, 3] + dy < y0:
                        continue
                    if _rect_meets_polys(x0, y0, x1, y1, verts, starts[p:p + 2], dx, dy):
                        hit = True
                        break
                if hit:
                    break
            if hit:
                cnt[c] += 1
                if first[c] == T1:
                    first[c] = k
    return cnt, first


@numba.njit(cache=True, parallel=True)
def pin_contacts_kernel(cx, cy, inv, hx, hy, rel_k, rel_x, rel_y, aim_f, ca, sa, spawn, step, seg):
    """ForumPlanner._pin_contacts' loop: per row (cx, cy, inv [n, T1]) the first frame a pin released at frame
    rel_k[j] from (rel_x[j], rel_y[j]), aimed at the row's centre aim_f frames before (rotated by each (ca, sa)),
    spawned `spawn` u out and flying `step` u a frame, its segment points `seg` along it, meets the box of half extents
    hx, hy; T1: none."""
    n, T1 = cx.shape
    first = np.full(n, T1, np.int64)
    for i in numba.prange(n):
        for j in range(len(rel_k)):
            kr = rel_k[j]
            if kr >= T1 - 1:
                continue
            ka = max(kr - aim_f, 0)
            ax0, ay0 = cx[i, ka] - rel_x[j], cy[i, ka] - rel_y[j]
            nrm = max(math.hypot(ax0, ay0), 1e-6)
            for q in range(len(ca)):
                ux = (ax0 * ca[q] - ay0 * sa[q]) / nrm
                uy = (ax0 * sa[q] + ay0 * ca[q]) / nrm
                ox, oy = rel_x[j] + spawn * ux, rel_y[j] + spawn * uy
                for k in range(kr, min(T1, first[i])):
                    if inv[i, k]:
                        continue
                    d = step * (k - kr)
                    hit = False
                    for g in range(len(seg)):
                        px = ox + ux * (d + seg[g])
                        py = oy + uy * (d + seg[g])
                        if abs(px - cx[i, k]) <= hx and abs(py - cy[i, k]) <= hy:
                            hit = True
                            break
                    if hit:
                        first[i] = k
                        break
    return first


def committed_fine_share(f, box: np.ndarray, inv: np.ndarray, rows: np.ndarray, fr: np.ndarray,
                         tk: np.ndarray) -> np.ndarray:
    """[len(rows)] the share of the frames fr each row's nominal box centre spends in the committed fine placements
    (MultiForecast.pm["committed"]: the current attacks' templates at their anchor, entry known to FINE_MAX_BINS),
    invulnerable frames clear; zeros without such placements (or for a forecast without them)."""
    pm = getattr(f, "pm", None)
    out = np.zeros(len(rows))
    if pm is None or not len(rows) or not len(pm.get("owner", ())):
        return out
    sel = np.asarray(pm["committed"], bool)
    if not sel.any():
        return out
    b = box[rows][:, fr]
    occ = f._fine_occ(0.5 * (b[..., 0] + b[..., 2]), 0.5 * (b[..., 1] + b[..., 3]), tk[fr], sel) & ~inv[rows][:, fr]
    return occ.mean(axis=1)


def seen_polys(ws) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """The damage polygons the hero could meet now: every entity's active damage boxes (oracle: enabled colliders
    able to deal damage; vision: the detected boxes), with the entity's velocity. Returns (verts [m, 2], starts
    [n + 1], bounding boxes [n, 4], velocities [n, 2])."""
    vs, st, bb, vel = [], [0], [], []
    for e in getattr(ws, "entities", None) or ():
        polys = [b.poly for b in e.dmg_boxes if b.active and len(b.poly) >= 3]
        if not polys:
            continue
        v = e.vel.v if getattr(e.vel, "conf", 1.0) > 0 else (0.0, 0.0)
        for poly in polys:
            a = np.asarray(poly, np.float64).reshape(-1, 2)
            vs.append(a)
            st.append(st[-1] + len(a))
            bb.append((a[:, 0].min(), a[:, 1].min(), a[:, 0].max(), a[:, 1].max()))
            vel.append((float(v[0]), float(v[1])))
    if not vs:
        return np.zeros((0, 2)), np.zeros(1, np.int64), np.zeros((0, 4)), np.zeros((0, 2))
    return (np.ascontiguousarray(np.concatenate(vs)), np.array(st, np.int64), np.array(bb, np.float64),
            np.array(vel, np.float64))


@numba.njit(cache=True, parallel=True)
def _forum_score_kernel(box, flags, mode, latched, face0, tbox, tok, tw, vr, vl, st, win, wall_l, wall_r, wv, stance_x,
                        rx, rv, boss_x, max_hits, J, hits, first_f, first_t, first_k, first_face, risk, unmod,
                        down_slash, combo_f, sw_f, sw_k, sw_face, real, nh, gonly):
    """J per row on the nominal lane over K targets (tbox [K, T1, 4], tok [K, T1], weights tw [K, 4] by the slash kind
    side / up / wall / down: GoalPrefs.hit_kw, else the target's one weight for every kind): the crest's side /
    up / wall / down slash polygons in their active windows against each target's box (an attack counts each target it
    meets once, weighted); nh: the hits on targets with real[t] (enemies, not bells), unweighted (the effective mask
    loss's hits landed); first_f / first_t / first_k / first_face: the first predicted hit (frame, target, kind,
    facing); sw_f / sw_k / sw_face: the first swing (frame, kind, facing); unmod: an attack pressed while dashing or
    sprinting (the dash stab, not modelled) or, combo_f > 0 (Wanderer), up to combo_f frames after a dash / sprint frame
    (HeroController.Attack: inside wandererDashComboWindowTimer the press is the WANDERER DASH COMBO). down_slash: the
    crest's down attack is a slash (DownSlashTypes.Slash: an ATTACKING swing pressed with down in the air). gonly[t]
    (SSBOT_FORUM_JUMP_BEHIND, GoalPrefs.ground_hit): a hit on target t counts (h, nh) only when the swing was pressed
    on the ground; the first-hit fields still record it (the hit branch's recoil)."""
    N, T1 = flags.shape
    K = tbox.shape[0]
    for c in numba.prange(N):
        face = face0
        fc = np.empty(T1, np.int64)
        cxs = np.empty(T1)
        cys = np.empty(T1)
        for k in range(T1):
            if k > 0:
                m = latched[c, k - 1]
                d = 1 if m & kin.B_RIGHT else (-1 if m & kin.B_LEFT else 0)
                if d != 0 and mode[c, k - 1] == M_NORMAL and (flags[c, k - 1] & F_ATTACKING) == 0:
                    face = d
            fc[k] = face
            cxs[k] = 0.5 * (box[c, k, 0] + box[c, k, 2])
            cys[k] = 0.5 * (box[c, k, 1] + box[c, k, 3])
        h = 0.0
        presses = 0
        jumps = 0
        for k in range(1, T1):
            jl = (latched[c, k - 1] & B_JUMP) != 0
            jp = k > 1 and (latched[c, k - 2] & B_JUMP) != 0
            if jl and not jp:
                jumps += 1
            if (latched[c, k - 1] & B_ATTACK) != 0 and (k < 2 or (latched[c, k - 2] & B_ATTACK) == 0):
                if mode[c, k - 1] == M_DASH or mode[c, k - 1] == M_SPRINT or mode[c, k] == M_DASH:
                    unmod[c] = True
                for j in range(1, combo_f + 1):
                    if k - 1 - j < 0:
                        break
                    if mode[c, k - 1 - j] == M_DASH or mode[c, k - 1 - j] == M_SPRINT:
                        unmod[c] = True
                        break
            att = (flags[c, k] & F_ATTACKING) != 0 and (flags[c, k - 1] & F_ATTACKING) == 0
            dsk = mode[c, k] == M_RPR_DS and mode[c, k - 1] != M_RPR_DS
            if not (att or dsk):
                continue
            presses += 1
            if dsk:
                s, kind = 3, K_DOWN
            elif (latched[c, k - 1] & B_UP) != 0:
                s, kind = 1, K_UP
            elif down_slash and (latched[c, k - 1] & B_DOWN) != 0 and (flags[c, k - 1] & F_GROUND) == 0:
                s, kind = 3, K_DOWN
            elif (flags[c, k] & F_GROUND) == 0 and (box[c, k, 0] - wall_l < WALL_TOUCH_U
                                                     or wall_r - box[c, k, 2] < WALL_TOUCH_U):
                s, kind = 2, K_WALL
            else:
                s, kind = 0, K_SIDE
            a, b = st[s], st[s + 1]
            if sw_f[c] < 0:
                sw_f[c], sw_k[c], sw_face[c] = k, kind, fc[k]
            for t in range(K):
                got = False
                for j in range(k + win[s, 0], min(T1, k + win[s, 1])):
                    if not tok[t, j]:
                        continue
                    vv = vr if fc[j] > 0 else vl
                    if _meets(tbox[t, j, 0], tbox[t, j, 1], tbox[t, j, 2], tbox[t, j, 3], vv, a, b, cxs[j], cys[j]):
                        got = True
                        if first_f[c] < 0 or j < first_f[c]:
                            first_f[c], first_t[c], first_k[c], first_face[c] = j, t, kind, fc[j]
                        break
                if got:
                    if gonly[t] and (flags[c, k - 1] & F_GROUND) == 0:
                        continue
                    h += tw[t, kind - 1]
                    if real[t]:
                        nh[c] += 1.0
        h = min(h, max_hits)
        waste = max(presses - h, 0.0)
        x_end = cxs[T1 - 1]
        r = np.interp(x_end, rx, rv)
        d_mean = 0.0
        for k in range(T1):
            d_mean += abs(cxs[k] - stance_x)
        d_mean /= T1
        v = wv[0] * h - wv[1] * waste - wv[2] * jumps - wv[3] * (0.5 * abs(x_end - stance_x) + 0.5 * d_mean) \
            - wv[4] * r
        if boss_x == boss_x:
            want = 1 if boss_x > x_end else -1
            if fc[T1 - 1] == want:
                v += wv[5]
        if flags[c, T1 - 1] & F_GROUND:
            v += wv[6]
        J[c] = v
        hits[c] = h
        risk[c] = r


@numba.njit(cache=True, parallel=True)
def _ds_contact_kernel(box, flags, mode, latched, face0, tbox, tok, treal, vr, vl, a, b, w0, w1, k_from, grow, shifts,
                       tb0, out_k, out_j, out_t, out_rob):
    """The family's down slash contacts (dslash, task 1v1 G3): per row, its first down slash in the air (an ATTACKING
    swing started with down held, off the ground, as _forum_score_kernel's K_DOWN) at or after state k_from[c]: the
    swing's start (out_k), the first frame of its active window [k + w0, k + w1) whose blade (the down polygons,
    facing as the scorer's) meets a real target's box grown by `grow` (out_j, out_t; -1: none) and whether the contact
    holds with that target's box path shifted by every frame offset in `shifts` and, with shifts, with the target
    stopped where it is now (tb0 [K, 4]: the lunge-phase variant; the predicted body moves on at its present velocity,
    a lunge may end any frame) (out_rob)."""
    N, T1 = flags.shape
    K = tbox.shape[0]
    for c in numba.prange(N):
        out_k[c] = -1
        out_j[c] = -1
        out_t[c] = -1
        out_rob[c] = False
        face = face0
        fc = np.empty(T1, np.int64)
        for k in range(T1):
            if k > 0:
                m = latched[c, k - 1]
                d = 1 if m & kin.B_RIGHT else (-1 if m & kin.B_LEFT else 0)
                if d != 0 and mode[c, k - 1] == M_NORMAL and (flags[c, k - 1] & F_ATTACKING) == 0:
                    face = d
            fc[k] = face
        for k in range(max(1, k_from[c]), T1):
            if not ((flags[c, k] & F_ATTACKING) != 0 and (flags[c, k - 1] & F_ATTACKING) == 0):
                continue
            if (latched[c, k - 1] & B_DOWN) == 0 or (flags[c, k - 1] & F_GROUND) != 0 \
                    or (latched[c, k - 1] & B_UP) != 0:
                continue
            out_k[c] = k
            for j in range(k + w0, min(T1, k + w1)):
                vv = vr if fc[j] > 0 else vl
                cx = 0.5 * (box[c, j, 0] + box[c, j, 2])
                cy = 0.5 * (box[c, j, 1] + box[c, j, 3])
                for t in range(K):
                    if not treal[t] or not tok[t, j]:
                        continue
                    if _meets(tbox[t, j, 0] - grow, tbox[t, j, 1] - grow, tbox[t, j, 2] + grow, tbox[t, j, 3] + grow,
                              vv, a, b, cx, cy):
                        out_j[c] = j
                        out_t[c] = t
                        break
                if out_j[c] >= 0:
                    break
            if out_j[c] >= 0:
                t = out_t[c]
                rob = True
                for si in range(len(shifts)):
                    got = False
                    for j in range(k + w0, min(T1, k + w1)):
                        jj = min(max(j + shifts[si], 0), T1 - 1)
                        if not tok[t, jj]:
                            continue
                        vv = vr if fc[j] > 0 else vl
                        cx = 0.5 * (box[c, j, 0] + box[c, j, 2])
                        cy = 0.5 * (box[c, j, 1] + box[c, j, 3])
                        if _meets(tbox[t, jj, 0], tbox[t, jj, 1], tbox[t, jj, 2], tbox[t, jj, 3], vv, a, b, cx, cy):
                            got = True
                            break
                    if not got:
                        rob = False
                        break
                if rob and len(shifts) and tb0.shape[0] > 0:
                    got = False
                    for j in range(k + w0, min(T1, k + w1)):
                        vv = vr if fc[j] > 0 else vl
                        cx = 0.5 * (box[c, j, 0] + box[c, j, 2])
                        cy = 0.5 * (box[c, j, 1] + box[c, j, 3])
                        if _meets(tb0[t, 0], tb0[t, 1], tb0[t, 2], tb0[t, 3], vv, a, b, cx, cy):
                            got = True
                            break
                    rob = got
                out_rob[c] = rob
            break


@dataclass
class DsRows:
    """The family's rows of one tick (ForumPlanner._ds_rows)."""
    cmd: np.ndarray            # [n, T] the planner rows
    names: list
    ext: list                  # [n] the whole template (masks after the prefix; longer than T for a long chain row)
    ev: np.ndarray             # [n, P + T] the planner lane's events (the certain bounces; 0 on the other rows)
    cert: np.ndarray           # [n] the certain-hit rule applies (bounce branch only)
    c1: np.ndarray             # [n] the first strike's contact (state index), c2 the second's (-1: none)
    c2: np.ndarray
    tgt: np.ndarray            # [n] the first strike's target iid
    extra: np.ndarray          # [n] certain strikes past the planner's horizon (credited to the ranking)
    lane: dict | None          # the certain rows' bounce lanes over P + T (phys, pos, vel, mode, flags, box, final)
    n_tpl: int = 0
    n_pass: int = 0
    n_chain: int = 0
    ms: float = 0.0


def forum_kill_hp(mf, z: float = KILL_Z) -> float | None:
    """U's subject in the Forum (forum_planner_plan §4.2 "最后一击"): the least HP the battle's last members may have
    when one blow may end the battle (the 1.85 s slow motion that cannot be paused): the final wave running (or every
    wave done) and every member still alive at or below that blow, so the max over them of hp_est - z sigma; None while
    other waves are to come (an ordinary kill's freeze is YELLOW's, forum_yellow_kill_hp). mf: the MultiForecaster
    (hp_est from the hits seen; never ents.hp)."""
    w = getattr(mf, "waves", None)
    if w is None or not (w.done or w.wave >= len(FORUM_WAVES) - 1) or w.queued is not None:
        return None
    lo = [max(0.0, tr.hp_est - z * tr.hp_sd) for tr in mf.trackers.values()
          if tr.in_play and not tr.dead and tr.tk in {t for t in FORUM_WAVES[-1].types}]
    return max(lo) if lo else None


KILL_FREEZE_KINDS = ("BigEnemyDeathSlow", "EnemyBattleEndSlow", "EnemyDeath")
# SSBOT_FORUM_KF=any: every freeze that started on a kill frame counts (the integration's rule before forum.md §23)
KF_ANY = os.environ.get("SSBOT_FORUM_KF", "kill").strip().lower() == "any"


def kill_freeze_s(path=None, any_kind: bool | None = None) -> dict[str, float]:
    """The longest freeze a kill of each Forum type was seen to start (forum_products kill_freeze.json, s of real
    time), 0 for a type whose kills never froze. Only the kill's own freezes count (KILL_FREEZE_KINDS: the enemy's
    death slow motion, forum.md 12.3: the Clapper's alone); the hero's freezes that happened to start on a kill frame
    (NailClashEffect 0.4 s, StartRecoil 0.25 s, BindBreak, QuickFreeze: a clash, a hit taken, the hero's own) are not
    the kill's (task wave-0 de-saturation, forum.md §23: counting them gave every wave-0 type a 0.4 s "kill freeze", so
    YELLOW's kill rule withheld every slash that might finish an Envoy, Choristor or Reed). any_kind (default
    SSBOT_FORUM_KF=any): every kind counts, the rule before."""
    import json
    from ssbot.combat.enemy_tables import FORUM_DIR
    p = path or FORUM_DIR / "kill_freeze.json"
    d = json.loads(p.read_text("utf-8"))
    out = {tk: 0.0 for tk in FORUM_TYPES}
    for k, v in (d.get("length") or {}).items():
        tk, _, kind = k.partition("|")
        if not (KF_ANY if any_kind is None else any_kind) and kind not in KILL_FREEZE_KINDS:
            continue
        ms = (v.get("ms") or {}).get("max")
        if ms is not None:
            out[tk] = max(out.get(tk, 0.0), float(ms) / 1e3)
    return out


def forum_yellow_kill_hp(mf, freeze: dict[str, float], z: float = KILL_Z, min_freeze_s: float = 0.0
                         ) -> float | None:
    """YELLOW's per-enemy kill freeze (forum_planner_plan §4.4 item 7): the least HP (hp_est - z sigma) over the enemies
    in play whose type's kill was seen to freeze the game longer than min_freeze_s (kill_freeze_s); the supervisor's
    kill_prims withholds the damaging primitives whose next landed hit may take one of them to 0. None: none."""
    lo = [max(0.0, tr.hp_est - z * tr.hp_sd) for tr in mf.trackers.values()
          if tr.in_play and not tr.dead and freeze.get(tr.tk, 0.0) > min_freeze_s]
    return min(lo) if lo else None


KIND_SLOT = {K_SIDE: "side", K_UP: "up", K_WALL: "wall", K_DOWN: "down"}
_UNDER: tuple | None = None


def under_gains(path=None) -> tuple[dict, dict]:
    """The under-flier bonus's rates (track A "under", the person's note ③ of 2026-10-08; knowledge below.json: the
    share of attack instances committed in the air that touch a hero on the floor at dx from the commit point, the
    hazards they throw included): ({type: gain}, {(type, family): gain}), gain = the rate 3 u in front less the rate
    below, clipped at 0; a type's gain is the instance-weighted mean over its families that have both (forum.md §26:
    Bellbearer 0.085, Reed 0.032 (stab 0.066, throw 0.083), Tiny 0.126, Clawmaiden 0.014, Minister and Maestro 0)."""
    global _UNDER
    if _UNDER is not None and path is None:
        return _UNDER
    import json
    from ssbot.combat.enemy_tables import FORUM_DIR
    d = json.loads(Path(path or FORUM_DIR / "below.json").read_text("utf-8"))["by_family"]
    fam, acc = {}, {}
    for k, v in d.items():
        tk, fm = k.split("/", 1)
        a, b = v.get("with thrown hazards: dx +3"), v.get("with thrown hazards: dx +0")
        if a is None or b is None:
            continue
        g = float(a) - float(b)
        fam[(tk, fm)] = max(0.0, g)
        n = float(v.get("instances") or 0)
        s0, w0 = acc.get(tk, (0.0, 0.0))
        acc[tk] = (s0 + n * g, w0 + n)
    out = ({tk: max(0.0, s0 / w0) for tk, (s0, w0) in acc.items() if w0 > 0}, fam)
    if path is None:
        _UNDER = out
    return out


# The hit enemy's knockback (track A "kb"; forum.md §26, the R0 + R1 caches, 395 fights: the transform's displacement
# after a nail hit less its own motion before it, median over the hits by type x slash x state): a side slash pushes it
# away from the hero about 0.45 u a frame for 8 frames (3.6 u), an up slash up about 0.375 u a frame (3.0 u); the
# Maestro about 0.65 of that, the Clapper 0.2 sideways and nothing up; a guard (the Minister's Parry Stance -> Parry
# Block, the Reed's Defend -> Block) 1.3 / 0.95 u sideways and 0.25 / 0.5 u up (taken as 0 up); states whose median at
# 12 frames is under 2 u (a dash, a stab, a spin, a death fall) none. Frames after the hit -> u (KB_PROFILE) x scale.
KB_SIDE_U_F, KB_UP_U_F, KB_FRAMES = 0.45, 0.375, 8
KB_SCALE = {"Song Pilgrim Maestro": (0.65, 0.65), "Song Heavy Sentry": (0.2, 0.0)}       # (side, up)
KB_GUARD = {("Song Administrator", "Parry Stance"): (0.35, 0.0), ("Song Administrator", "Parry Stance Antic"): (0.35, 0.0),
            ("Song Reed", "Defend"): (0.25, 0.0)}
KB_NONE = frozenset({
    ("Song Administrator", "Attack"), ("Song Administrator", "Parry Block"), ("Song Administrator", "Parry Slash 1"),
    ("Song Administrator", "Parry Slash 2"), ("Song Administrator", "Parry Slash 3"),
    ("Song Administrator", "Parry Slash 4"), ("Song Reed", "Block"), ("Song Reed", "Multihit Clashed"),
    ("Song Reed", "Parry Slash"), ("Song Reed", "Stab 1"), ("Song Reed", "Stab 2"), ("Song Reed", "Stab 3"),
    ("Song Reed", "Stab 4"), ("Song Reed", "Stab 5"), ("Song Automaton Tiny", "Defend Buzz"),
    ("Song Automaton Tiny", "Wall Bonk"), ("Song Automaton Tiny", "Die"), ("Song Automaton Tiny", "Brake"),
    ("Song Handmaiden", "Slash 1"), ("Song Handmaiden", "Slash 4"), ("Song Handmaiden", "Slash 5"),
    ("Song Pilgrim 01", "JumpSlash Antic"), ("Song Pilgrim 03", "Jump Spin"), ("Song Pilgrim 03", "Hop Back"),
    ("Song Pilgrim 03", "Slash End"), ("Song Pilgrim 03", "ComboSlash Antic2"), ("Song Pilgrim 03", "Slash 2"),
    ("Song Pilgrim 03", "Jump Rise")})


def knockback(tk_name: str, state: str | None, kind: int, face: int, n: int, scale: float = 1.0
              ) -> tuple[np.ndarray, np.ndarray] | None:
    """(dx [n], dy [n]) the hit enemy is pushed by over the n frames from the hit frame on (frame 0 = the hit), or None
    when the hit pushes it by nothing measurable (a down slash, a state of KB_NONE, a type with no push that way)."""
    if kind == K_DOWN or (tk_name, state) in KB_NONE:
        return None
    side = kind in (K_SIDE, K_WALL)
    g = KB_GUARD.get((tk_name, state))
    sx, sy = g if g is not None else KB_SCALE.get(tk_name, (1.0, 1.0))
    a = sx * KB_SIDE_U_F if side else sy * KB_UP_U_F
    if a <= 0.0:
        return None
    d = scale * a * np.minimum(np.arange(n), KB_FRAMES)
    return (face * d, np.zeros(n)) if side else (np.zeros(n), d)


def _wilson_lb(k: float, n: float, z: float = 1.96) -> float:
    if n <= 0:
        return 0.0
    p = k / n
    return max(0.0, (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n))


@dataclass
class ClashTable:
    """The EV_CLASH branch's rates per (type, attack family, slot) (knowledge/<build>/enemies/forum/clash.json,
    ssbot.tools.forum_clash_stats --table), over the recorded swings whose clash reach met the enemy's attack first or
    whose active window held its first contact, in the family's clashable states: p (p_fail) the Wilson 95 % upper
    bound of the share hit anyway, q (p_clash_lb) the lower bound of the share that clashed (a setup that neither
    clashed nor was hit gave none of the clash's effects), both at the attack instances behind them; crest_rows: a
    crest's own bounds where it has min_n instances. states: the Control states a family's clashes happen in (a contact
    from another state of it is not clashable; None for a table without them: the whole family). A key that is not
    there is not clashable (no clash collider in the family, the type's moves never clash: every body, the Clapper, the
    Clawmaiden spear, the Bellbearer bell, the Tinies; or too few samples)."""
    p: dict
    q: dict = field(default_factory=dict)
    states: dict = field(default_factory=dict)
    crest_rows: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path=None) -> "ClashTable":
        import json
        from ssbot.combat.enemy_tables import FORUM_DIR
        d = json.loads(Path(path or FORUM_DIR / CLASH_FILE).read_text("utf-8"))
        min_n = int(d.get("min_n") or 10)
        p, q, cr = {}, {}, {}
        for k, v in (d.get("p_fail") or {}).items():
            key = tuple(k.split("|"))
            p[key] = float(v["p_fail"])
            # a table from before the clash share: the lower bound from its counts
            q[key] = float(v["p_clash_lb"]) if "p_clash_lb" in v else _wilson_lb(float(v.get("clash") or 0),
                                                                                  float(v.get("n") or 0))
            for crest, c in (v.get("by_crest") or {}).items():
                if "p_clash_lb" in c and int(c.get("n_eff") or 0) >= min_n:
                    cr[(crest,) + key] = (float(c["p_fail"]), float(c["p_clash_lb"]))
        st = {tuple(k.split("|")): frozenset(v) for k, v in (d.get("clash_states") or {}).items()}
        return cls(p, q, st, cr)

    def p_fail(self, tk: str, family: str | None, slot: str) -> float | None:
        return None if family is None else self.p.get((tk, family, slot))

    def rate(self, tk: str, family: str | None, slot: str, crest: str | None = None) -> tuple[float, float] | None:
        """(p_fail, p_clash_lb), the crest's own where it has them; None: not clashable."""
        key = (tk, family, slot)
        if family is None or key not in self.p:
            return None
        return self.crest_rows.get((crest,) + key) or (self.p[key], self.q.get(key, 0.0))

    def clash_states(self, tk: str, family: str) -> frozenset | None:
        return self.states.get((tk, family)) if self.states else None

    def families(self) -> set[tuple[str, str]]:
        """(type, family) with a clashable slot."""
        return {(tk, fam) for tk, fam, _ in self.p}


def clash_windows(tt, family: str, state: str | None, t_entry: float | None, T0: float, clash_states: frozenset,
                  stop_states: frozenset, horizon: float) -> list[tuple[float, float, bool]]:
    """[(lo, hi, stop)]: the game-time spans in which an enemy now in `state` (entered at t_entry) of its attack
    `family` may be in each of the family's clashable states (TypeTable's logged dwell (min, max) and successors,
    inside the family: a decision state ends the attack), stop: that state is a PARRIED-catching one. Empty when no
    clashable state is current or ahead (a recovery state: Charge End, Stab Recover, ...). Capped at T0 + horizon."""
    fam = tt.families.get(family)
    if fam is None or state is None or t_entry is None or state not in fam.states:
        return []
    inside = set(fam.states)
    cap = T0 + horizon
    lo, hi = {state: t_entry}, {state: t_entry}

    def exits(s):
        dmin, dmax = tt.dwell.get(s, (0.0, horizon))
        if s == state:                           # still in it at T0: it may end any time from then
            return max(t_entry + dmin, T0), max(t_entry + dmax, T0)
        return lo[s] + dmin, hi[s] + dmax
    for _ in range(len(inside)):
        changed = False
        for s in list(lo):
            x_lo, x_hi = exits(s)
            for t in tt.succ.get(s, ()):
                if t not in inside or t in tt.decision_states or x_lo > cap:
                    continue
                if t not in lo or x_lo < lo[t]:
                    lo[t] = x_lo
                    changed = True
                h2 = min(x_hi, cap)
                if t not in hi or h2 > hi[t]:
                    hi[t] = h2
                    changed = True
        if not changed:
            break
    out = []
    for s in sorted(clash_states & set(lo)):
        out.append((lo[s], min(exits(s)[1], cap), s in stop_states))
    return out


def swings(flags: np.ndarray, mode: np.ndarray, latched: np.ndarray, box: np.ndarray, face0: int,
           down_slash: bool) -> list[tuple[int, int, int]]:
    """(frame, kind, facing) of every swing of one row on its nominal lane, as _forum_score_kernel finds them."""
    out = []
    face = face0
    T1 = len(flags)
    for k in range(1, T1):
        m = int(latched[k - 1])
        d = 1 if m & kin.B_RIGHT else (-1 if m & kin.B_LEFT else 0)
        if d != 0 and mode[k - 1] == M_NORMAL and (flags[k - 1] & F_ATTACKING) == 0:
            face = d
        att = (flags[k] & F_ATTACKING) != 0 and (flags[k - 1] & F_ATTACKING) == 0
        dsk = mode[k] == M_RPR_DS and mode[k - 1] != M_RPR_DS
        if not (att or dsk):
            continue
        if dsk:
            kind = K_DOWN
        elif m & B_UP:
            kind = K_UP
        elif down_slash and (m & B_DOWN) and not (flags[k - 1] & F_GROUND):
            kind = K_DOWN
        elif not (flags[k] & F_GROUND) and (box[k, 0] - WALL_L < WALL_TOUCH_U or WALL_R - box[k, 2] < WALL_TOUCH_U):
            kind = K_WALL
        else:
            kind = K_SIDE
        out.append((k, kind, face))
    return out


class ForumPlanner(Planner):
    def __init__(self, params: HeroParams, terrain: Terrain2D, cfg: PlannerConfig | None = None,
                 fcfg: ForumConfig | None = None, crest: str = "Reaper"):
        self.fcfg = fcfg or ForumConfig()
        super().__init__(params, terrain, cfg or PlannerConfig(T=self.fcfg.T, variants=self.fcfg.variants))
        self.fsets = {p: cmod.build_forum(self.fcfg.T, p, clash=self.fcfg.clash, waits=self.fcfg.waits or self.fcfg.v2)
                      for p in cmod.POSTURES}
        # without control (hit-stop, recoil, a lock) the keys only queue: the core rows only (Planner's cands_nc)
        self.fsets_nc = {p: (cs.subset(core), core[core]) for p, (cs, core) in self.fsets.items()}
        self.crest = crest
        self._map = None                  # SSBOT_FORUM_SPECIAL_MAP: combat.forum_map.MapHelper
        self._chase_jc: dict = {}         # SSBOT_FORUM_CHASE: iid -> the tracker's last time in a jump cast
        if SPECIAL_MAP:
            # review: loaded here (or on the first tick with the arena's terrain: the policy builds the planner on an
            # empty one), not on the first tick near a Clapper (that tick stalled ~80 ms in the replays)
            from ssbot.combat import forum_map
            self._map = forum_map.MapHelper(self)
            self._map.preload()
        self.shapes = _shapes(crest)
        cfg_c = AttackTable.load(crest).config
        self.down_slash = cfg_c.get("down") == "Slash"
        self.combo_f = WANDERER_COMBO_F if crest == "Wanderer" else 0
        self.clash_tab = ClashTable.load() if self.fcfg.clash else None
        self.clash_fams = self.clash_tab.families() if self.clash_tab is not None else set()
        # the clash reach per kind: the slot's Clash Tink box (x0, x1, y0, y1; facing frame, from the hero collider
        # centre), else its damage polygons' bounding box
        tab = AttackTable.load(crest)
        self.reach = {}
        for kind, s in ((K_SIDE, "normal"), (K_UP, "up"), (K_WALL, "wall"), (K_DOWN, "down")):
            sh = tab.shapes.get(s) or tab.shapes.get("normal")
            if sh.clash_box:
                self.reach[kind] = tuple(float(v) for v in sh.clash_box)
            else:
                p = np.concatenate(sh.polys)
                self.reach[kind] = (float(p[:, 0].min()), float(p[:, 0].max()), float(p[:, 1].min()),
                                    float(p[:, 1].max()))
        self._clash_lvl_ms = 0.0          # the clash pass's first level, running mean (its deadline check)
        self.esc_batch_s = 0.003          # the escape check's batch, running mean (its deadline check)
        self.esc_cut = False
        self.prev_esc_unsafe = False      # the last chosen row was S = 1 by the escape check (a carried CONTINUE keeps it)
        self.audit = EnvelopeAudit()
        self.last_info: dict = {}
        self.measurement_enabled = False
        self.measurement_result = None
        self.debug = False                # offline forensics (tools.forum_hit_forensics): last_info["dbg"] keeps the
        #                                   tick's rows (nominal boxes, flags, J, ...); no effect on any decision
        self.last_sel: dict | None = None
        self.tv = TerminalValue(params) if self.fcfg.terminal else None
        self._two: dict = {}

    def warm_kernels(self) -> None:
        """Planner.warm_kernels and the "seen" key's kernel (it runs only on FORCED_RISK ticks: a first call mid-fight
        compiles past the oracle's brain-lost watchdog)."""
        super().warm_kernels()
        box = np.zeros((2, 5, 4))
        box[..., 2:] = 1.0
        args = (box, np.zeros((2, 5), np.bool_), np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]),
                np.array([0, 3], np.int64), np.array([[0.0, 0.0, 1.0, 1.0]]), np.zeros((1, 2)),
                np.arange(5, dtype=np.float64), np.arange(2, dtype=np.int64), 0.0)
        seen_contacts(*args)
        # "+s" and the aimed pins (the smoke of 2026-10-08 evening: a 1.8 s first call mid-fight)
        seen_contacts_swept(*args, 1.0 / 60.0, SEEN_SWEEP_MIN_U_S)
        z = np.zeros((2, 5))
        pin_contacts_kernel(z, z, np.zeros((2, 5), np.bool_), 0.5, 0.5, np.array([1], np.int64), np.zeros(1),
                            np.zeros(1), PIN_AIM_F, np.ones(1), np.zeros(1), PIN_SPAWN_U, 0.5, np.zeros(5))
        # SG8 (stalls; forum.md 64): the knockback hull (kin_jit.kb_hull_par / kb_hull / kb_hull_one / near) runs only
        # on ticks with hazards or soft gates; live its first call (an airborne hit) compiled 1.9 s mid-fight
        b2 = np.zeros((2, 5, 4))
        b2[..., 2:] = 1.0
        b2[1] += 3.0
        for th in sorted({1, max(int(self.cfg.threads), 1)}):
            knockback_hull(b2, self.params, self.terrain, threads=th)

    # ---- scoring ----

    def _forum_targets(self, ws, f, tk: np.ndarray, prefs) -> tuple[np.ndarray, np.ndarray, np.ndarray, list]:
        hx, hy = (float(ws.hero.pos.v[0]), float(ws.hero.pos.v[1])) if ws is not None and ws.hero is not None \
            else (0.0, 0.0)
        allt = f.targets(tk)
        tg = [t for t in allt if not t.hazard]
        d = [math.hypot(0.5 * (t.box[0, 0] + t.box[0, 2]) - hx, 0.5 * (t.box[0, 1] + t.box[0, 3]) - hy) for t in tg]
        # every enemy in reach: the first hit (the hit branch's) can be on any of them (a 5th-nearest Tiny of a
        # cluster); only the K_tgt nearest are scored (weight 0 for the rest: J, hits and waste unchanged)
        keep = [t for _, t in sorted(zip(d, tg), key=lambda z: z[0]) if _ <= TARGET_REACH_U]
        if self.fcfg.bell_hits:
            # the bells in reach after them, weight 0: a swing that meets one first knocks it back (the hit branch
            # takes it out of the support from the hit on: forum.md bell paragraph, the hit-back bells)
            for t in allt:
                if t.hazard and math.hypot(0.5 * (t.box[0, 0] + t.box[0, 2]) - hx,
                                           0.5 * (t.box[0, 1] + t.box[0, 3]) - hy) <= TARGET_REACH_U:
                    keep.append(t)
        T1 = len(tk)
        if not keep:
            return np.zeros((0, T1, 4)), np.zeros((0, T1), bool), np.zeros((0, 4)), []
        hw = getattr(prefs, "hit_w", None) or {}
        # per slash kind (side, up, wall, down): GoalPrefs.hit_kw (the L2 guard rules: an up slash on a Minister's
        # stance may score where a side slash must not), else the target's one weight
        kw = getattr(prefs, "hit_kw", None) or {}
        nohit = getattr(prefs, "no_hit", None) or ()      # SSBOT_FORUM_JUMP_BEHIND (SP3): weight 0 (and not real)
        tw = np.zeros((len(keep), 4))
        slot: dict = {}                       # enemy iid -> its scoring slot (a guard stance's copy shares its body's)
        for k, t in enumerate(keep):
            if t.hazard:
                continue
            if t.iid not in slot:
                slot[t.iid] = len(slot)
            if slot[t.iid] < self.fcfg.K_tgt and not getattr(t, "blocked", False) and t.iid not in nohit:
                w4 = kw.get(t.iid)
                tw[k] = w4 if w4 is not None else float(hw.get(t.iid, 1.0))
        tb = np.ascontiguousarray(np.stack([t.box for t in keep]), np.float64)
        if special_mode.MOVE_HITS:
            tb = self._move_hit_paths(f, keep, tb)
        return (tb, np.ascontiguousarray(np.stack([t.ok for t in keep])), tw, keep)

    def _move_hit_paths(self, f, keep: list, tbox: np.ndarray) -> np.ndarray:
        """SSBOT_FORUM_MOVE_HITS (task 1v1 G4, 5b): the scorer's body of an enemy in a tracked move (attack_range
        Segmenter instance with a template) carried by the move template's displacement still to come
        (RangeTable.position, vectorized; the mean over the branches the move may take, the instance's own once known),
        not moved on at its present velocity (most Forum moves carry the body 2-19 u: G3 found most family rows on the
        slam 'hitting' 6-11 u in front of the Clapper). tbox [K, T1, 4] -> a copy with those targets' paths."""
        trk = getattr(getattr(f, "rs", None), "trk", None)
        now = getattr(trk, "now", None) or {}
        tabs = getattr(trk, "tables", None) or {}
        if not now or not len(keep):
            return tbox
        from ssbot.combat.attack_range import bin_of
        out = None
        n = tbox.shape[1]
        for ti, t in enumerate(keep):
            if t.hazard or t.iid not in now:
                continue
            tk_, _e, inst = now[t.iid]
            tab = tabs.get(tk_)
            if inst is None or tab is None:
                continue
            b = bin_of(float(trk.T) - inst.t0)
            brs = (inst.branch,) if inst.branch else tuple(tab.spec.branches.get(inst.fam, ("main",)))
            ds_ = []
            for br in brs:
                tp = tab.templates.get((inst.fam, br))
                if tp is None:
                    continue
                bb = np.clip(b + np.arange(n), 0, tp.nb - 1)
                du = np.asarray(tp.disp[bb, 0], np.float64)
                if tp.ratio is not None and inst.fam in tab.spec.aim:
                    du = np.asarray(tp.ratio[bb], np.float64) * float(tab.landing(inst.hero_du))
                lo, hi = tab.walls
                x = np.minimum(np.maximum(inst.x0 + inst.s * du, lo), hi)
                y = inst.y0 + np.asarray(tp.disp[bb, 1], np.float64)
                ds_.append(np.stack([x - x[0], y - y[0]], axis=1))
            if not ds_:
                continue
            d = np.mean(ds_, axis=0)
            if out is None:
                out = tbox.copy()
            out[ti] = tbox[ti, 0][None, :] + np.stack([d[:, 0], d[:, 1], d[:, 0], d[:, 1]], axis=1)
            self.audit.mh_targets += 1
        return tbox if out is None else out

    def _under_bonus(self, f, box: np.ndarray, keep: list) -> np.ndarray:
        """Track A "under" (the person's note ③ of 2026-10-08): J per row = w_under x sum over the flyers in reach of
        the rate gain of standing under it (under_gains: by its current attack family when that has one, else its
        type's) x the share of frames 1 .. T1 - 1 the row's box centre is under its body (within its half-width +
        under_dx_u, its body's bottom above the hero box's top). Scores only."""
        typ, fam = under_gains()
        mf = getattr(f, "_fc", None)
        trs = getattr(mf, "trackers", None) or {}
        cx = 0.5 * (box[..., 0] + box[..., 2])
        top = box[..., 3]
        out = np.zeros(box.shape[0])
        for t in keep:
            if t.hazard:
                continue
            tr = trs.get(t.iid)
            fm = tr.cur.family if tr is not None and tr.cur is not None and tr.cur.t_end is None else None
            g = fam.get((t.type_key, fm), typ.get(t.type_key, 0.0))
            if g <= 0.0:
                continue
            tb = np.asarray(t.box, np.float64)
            half = 0.5 * (tb[:, 2] - tb[:, 0]) + self.fcfg.under_dx_u
            under = (np.abs(cx - 0.5 * (tb[:, 0] + tb[:, 2])[None]) <= half[None]) & (tb[:, 1][None] > top) & \
                np.asarray(t.ok, bool)[None]
            out += g * under[:, 1:].mean(axis=1)
        return self.fcfg.w_under * out

    def _two_mask(self, f):
        """owner -> it has a 2-mask attack or a multi-hit chain (per type, from the tables: family damage >= 2 or a
        chain of more than one hit)."""
        from ssbot.combat.multi_forecast import _chain
        fc = f._fc
        tables = fc.tables
        if id(tables) not in self._two:
            two = set()
            for tk_, tt in tables.types.items():
                if any(fm.damage >= 2 or _chain(tables.chains, tk_, name)[0] > 1 for name, fm in tt.families.items()):
                    two.add(tk_)
            self._two = {id(tables): two}
        two = self._two[id(tables)]
        return lambda k: (k in fc.trackers and fc.trackers[k].tk in two)

    def _terminal(self, f, ctx):
        """The tick's body field (combat.terminal) and the kill value per enemy iid; (None, {}) without a multi-enemy
        forecast or with the terminal value off."""
        fc = getattr(f, "__dict__", {}).get("_fc")
        if self.tv is None or f.__dict__.get("boss_fc") is not None or not hasattr(fc, "trackers"):
            return None, {}
        fields = EnemyFields.from_bodies(f, self._two_mask(f))
        ws = getattr(f._fc, "_ws", None)
        if ws is None or ws.hero is None:
            return fields, {}
        dmg = getattr(getattr(ctx, "damage", None), "nail", None)
        hit = float(dmg) if dmg is not None and math.isfinite(dmg) and dmg > 0 else 9.0
        hx, hy = float(ws.hero.pos.v[0]), float(ws.hero.pos.v[1])
        return fields, fields.kill_value(hx, hy, hit)

    def _score_forum(self, ws, roll, latched, start, f, prefs, tk, ctx=None):
        w = prefs.weights
        N, T1 = roll.flags.shape
        face0 = 1 if np.asarray(start).reshape(kin.K, -1)[kin.FACE, 0] >= 0 else -1
        tbox, tok, tw, keep = self._forum_targets(ws, f, tk, prefs)
        t_tv = time.perf_counter()
        fields, kv = self._terminal(f, ctx)
        if kv and len(keep):
            tw = tw * np.array([1.0 + self.fcfg.w_K * kv.get(t.iid, 0.0) for t in keep])[:, None]
        wv = np.array([w.get("hit", 10.0), w.get("waste", 0.6), w.get("jump", 0.15), w.get("stance", 0.6),
                       w.get("risk", 3.0), w.get("face", 0.3), w.get("ground", 0.2), 0.0])
        rx = prefs.risk_x if len(prefs.risk_x) else np.zeros(1)
        rv = prefs.risk if len(prefs.risk) else np.zeros(1)
        out = dict(J=np.zeros(N), hits=np.zeros(N), first_f=np.full(N, -1, np.int64), first_t=np.full(N, -1, np.int64),
                   first_k=np.zeros(N, np.int64), first_face=np.zeros(N, np.int64), risk=np.zeros(N),
                   unmod=np.zeros(N, np.bool_), sw_f=np.full(N, -1, np.int64), sw_k=np.zeros(N, np.int64),
                   sw_face=np.zeros(N, np.int64), nh=np.zeros(N))
        vr, vl, st, win = self.shapes
        nohit = getattr(prefs, "no_hit", None) or ()
        real = np.array([not t.hazard and not getattr(t, "blocked", False) and t.iid not in nohit for t in keep],
                        np.bool_)
        gh = getattr(prefs, "ground_hit", None) or ()
        gonly = np.array([t.iid in gh and not t.hazard for t in keep], np.bool_)
        _forum_score_kernel(np.ascontiguousarray(roll.box), np.ascontiguousarray(roll.flags),
                            np.ascontiguousarray(roll.mode), np.ascontiguousarray(latched), face0,
                            tbox if len(keep) else np.zeros((0, T1, 4)), tok if len(keep) else np.zeros((0, T1), bool),
                            np.ascontiguousarray(tw, np.float64), vr, vl, st, win, WALL_L, WALL_R, wv,
                            float(prefs.stance_x),
                            np.ascontiguousarray(rx, np.float64), np.ascontiguousarray(rv, np.float64),
                            prefs.boss_x if prefs.boss_x is not None else np.nan,
                            float(prefs.max_hits) if prefs.max_hits is not None else np.inf,
                            out["J"], out["hits"], out["first_f"], out["first_t"], out["first_k"], out["first_face"],
                            out["risk"], out["unmod"], self.down_slash, self.combo_f, out["sw_f"], out["sw_k"],
                            out["sw_face"], real, out["nh"], gonly)
        out["targets"] = keep
        if "under" in self.fcfg.tac and len(keep):
            out["J_under"] = self._under_bonus(f, roll.box, keep)
            out["J"] += out["J_under"]
        if fields is not None:
            fc_ = self.fcfg
            c = 0.5 * (roll.box[:, T1 - 1, :2] + roll.box[:, T1 - 1, 2:])
            ecls = end_class(roll.flags[:, T1 - 1], roll.vel[:, T1 - 1, 1])
            E, trapped, ov, he = self.tv.rows(fields, c[:, 0], c[:, 1], ecls, float(tk[T1 - 1]))
            h = getattr(ctx, "h", None)
            hw = H_W_NONE if h is None else H_W.get(int(h), H_W_FAR)
            j_tv = fc_.w_E * E - fc_.w_trap * trapped - fc_.w_ov * ov - fc_.w_H * hw * he
            out["J"] += j_tv
            out.update(E=E, trapped=trapped, overlap=ov, hexp=he, kv=kv, J_tv=j_tv,
                       tv_ms=(time.perf_counter() - t_tv) * 1e3, field_ms=fields.ms)
        return out

    # ---- hit branches ----

    @staticmethod
    def _ds_evb(rows: np.ndarray, D0: int, ds) -> np.ndarray | None:
        """G3: the certain family rows' bounce events for the hit branch ([len(rows), P + T]; None: no such row)."""
        if ds is None or ds.lane is None:
            return None
        rows = np.asarray(rows, np.int64)
        w_ = (rows >= D0) & (rows < D0 + len(ds.cmd))
        if not w_.any():
            return None
        q = rows[w_] - D0
        if not ds.cert[q].any():
            return None
        out = np.zeros((len(rows), ds.ev.shape[1]), np.int64)
        out[np.flatnonzero(w_)] = np.where(ds.cert[q][:, None], ds.ev[q], 0)
        return out

    def _ds_anchor(self, sc: dict, ds, D0: int, r1, latched: np.ndarray, face0: int):
        """review2: the certain family rows' hit branch anchored at their certain contact (frame c1, target, a down
        slash, the facing then), not at the scorer's first hit: the scorer's body moves on at its present velocity (or
        the move's mean path), so it may see no hit on a certain row (no hit branch: the hit enemy's reaction and
        knockback were never checked) or one at another frame / on another target. Returns (sc with those rows'
        first-hit keys replaced (a copy), the certain rows, the certain rows whose target the scorer does not hold:
        S = 1)."""
        rows = D0 + np.flatnonzero(ds.cert)
        if not len(rows):
            return sc, rows, rows
        sc_h = dict(sc)
        for k_ in ("first_f", "first_t", "first_k", "first_face"):
            sc_h[k_] = np.asarray(sc[k_]).copy()
        idx = {getattr(t, "iid", None): i for i, t in enumerate(sc["targets"])}
        lost = []
        for r in rows:
            q = int(r) - D0
            ti = idx.get(int(ds.tgt[q]))
            if ti is None:
                lost.append(int(r))
                continue
            c = int(ds.c1[q])
            face = face0
            for k in range(1, c + 1):                 # the facing as _ds_contact_kernel's
                m = int(latched[r, k - 1])
                d = 1 if m & kin.B_RIGHT else (-1 if m & kin.B_LEFT else 0)
                if d and int(r1.mode[r, k - 1]) == M_NORMAL and not (int(r1.flags[r, k - 1]) & F_ATTACKING):
                    face = d
            f0 = int(sc["first_f"][r])
            self.audit.ds_anchor_nohit += int(f0 < 0)                  # (no hit branch before review2)
            self.audit.ds_anchor_moved += int(f0 >= 0 and (f0 != c or int(sc["first_t"][r]) != ti))
            sc_h["first_f"][r], sc_h["first_t"][r], sc_h["first_k"][r], sc_h["first_face"][r] = c, ti, K_DOWN, face
        self.audit.ds_anchor += len(rows) - len(lost)
        return sc_h, rows, np.asarray(lost, np.int64)

    def _hit_branch(self, f, start, latched, sc, rows, tk, enemy_only, budget, cap: bool = True, ev_base=None
                    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """The hit branch of rows (each with a predicted first hit): rolled out with the hit's effect from its frame,
        against the support and the hit enemy's reaction (every state its walk allows at the hit: reaction_states).
        budget: dict with hitfx / react counters (caps; cap False: none). Returns S [n], the branch's contact [n, T1]
        (the lanes' hull, the reaction included) and the rows the reaction cap left unchecked (S = 1)."""
        T = latched.shape[1]
        ev = np.zeros((len(rows), T), np.int64)
        kinds, faces, fr = sc["first_k"][rows], sc["first_face"][rows], sc["first_f"][rows]
        j = np.clip(fr, 0, T - 1)                # as Planner._hit_effects: the event from the hit frame's index
        bits = np.where(kinds == K_DOWN, kin.EV_POGO, np.where(kinds == K_UP, kin.EV_RECOIL_DOWN,
                                                                 np.where(faces > 0, kin.EV_RECOIL_L, kin.EV_RECOIL_R)))
        ev[np.arange(len(rows)), j] = bits
        if ev_base is not None:
            # G3: a certain family row's branch is its own bounce lane (the strikes' events), not one event at the
            # scorer's first hit
            hb_ = ev_base.any(axis=1)
            ev[hb_] = ev_base[hb_]
        rh = kin.rollout(start, latched[rows], self.params, self.terrain, events=ev, variants=self.fcfg.variants,
                         threads=self.cfg.threads)
        skip = ((rh.flags_all & F_INVULN) != 0) if enemy_only else np.zeros(rh.flags_all.shape, bool)
        tg = sc["targets"]
        bell = np.array([bool(getattr(tg[int(sc["first_t"][r])], "hazard", False)) for r in rows], bool) \
            if len(tg) else np.zeros(len(rows), bool)
        occ = np.zeros(rh.bound.shape[:2], bool)
        # track A "kb": the hit enemy pushed by its knockback from the hit frame on (its support moved with it: the
        # hero's hull moved the other way against its own support, the rest of the support as it is)
        # v2: always (the person 2026-10-10: knockback is a hit branch, not a replacement)
        kb_on = "kb" in self.fcfg.tac or (self.fcfg.v2 and getattr(f, "v2", False))
        kbs = self._kb_shifts(f, sc, rows, rh.bound.shape[1]) if kb_on else {}
        moved = np.zeros(len(rows), bool)
        bnd = rh.bound
        if kbs:
            moved[list(kbs)] = True
            bnd = rh.bound.copy()
            by_kb: dict = {}
            for n, (iid, key, dx, dy) in kbs.items():
                bnd[n, :, 0] -= dx
                bnd[n, :, 2] -= dx
                bnd[n, :, 1] -= dy
                bnd[n, :, 3] -= dy
                by_kb.setdefault((iid, key), []).append(n)
            for (iid, _), ns in by_kb.items():
                ns = np.array(ns, np.int64)
                # both the pushed and the unpushed support of the hit enemy: the push is the median knockback (no lower
                # bound) and a wall can stop it (review of forum push 2, task "zone fix" item 4)
                o = self._contacts(f, rh.bound[ns], tk, skip[ns])
                o |= self._contacts_only(f, bnd[ns], tk, skip[ns], [int(iid)])
                occ[ns] = o
            self.audit.kb_rows += len(kbs)
        plain = ~bell & ~moved
        if plain.any():
            occ[plain] = self._contacts(f, rh.bound[plain], tk, skip[plain])
        if bell.any():
            # a bell knocked back by the swing: the support without it from the hit on (MultiForecast.bell_redirected:
            # its redirected path, harmless to the hero), one query per (bell, hit frame, direction)
            by_b: dict = {}
            for n in np.flatnonzero(bell):
                r = rows[n]
                k_, face_ = int(sc["first_k"][r]), int(sc["first_face"][r])
                d_ = 2 if k_ == K_UP else (0 if k_ == K_DOWN else (1 if face_ > 0 else -1))
                by_b.setdefault((tg[int(sc["first_t"][r])].iid, int(fr[n]), d_), []).append(n)
            for (iid, hf, d_), ns in by_b.items():
                ns = np.array(ns, np.int64)
                t_hit = float(tk[min(hf, len(tk) - 1)])
                o = self._contacts_fn(f, rh.bound[ns], tk, skip[ns],
                                      lambda X, Y, iid=iid, t_hit=t_hit, d_=d_: f.bell_redirected(X, Y, tk, iid, t_hit,
                                                                                                    d_))
                occ[ns] = o if o is not None else self._contacts(f, rh.bound[ns], tk, skip[ns])
        s = occ.any(axis=1)
        # a first hit on a guard stance (stance_block: the Reed's Defend) is a tink that starts its counter, 1.25 s
        # long past the tink: beyond the horizon, so the branch cannot be shown safe (the person: a locked move only
        # when both outcomes are safe)
        if len(tg):
            blk = np.array([bool(getattr(tg[int(sc["first_t"][r])], "blocked", False)) for r in rows], bool)
            if blk.any():
                s |= blk
                for n in np.flatnonzero(blk):       # FORCED_RISK's ranking: in contact from the counter's first damage
                    occ[n, min(int(fr[n]) + stance_block.COUNTER_F, occ.shape[1] - 1):] = True
                self.audit.stance_rows += int(blk.sum())
        capped = np.zeros(len(rows), bool)
        # the hit enemy's reaction (hero_caused TOOK DAMAGE exits), one forecast per (enemy, hit frame)
        mf = getattr(f, "_fc", None)
        if mf is not None and hasattr(mf, "reaction_states"):
            cache = budget["react_cache"]
            by_rf: dict = {}                             # reaction key -> the rows meeting it (one query each)
            for n, r in enumerate(rows):
                if s[n]:
                    continue
                t = tg[int(sc["first_t"][r])]
                key = (t.iid, int(fr[n]))
                rf = cache.get(key, False)               # False: not looked at yet; None: no reaction
                if rf is False:
                    t_react = f.origin_t + float(tk[min(fr[n], len(tk) - 1)])
                    to = mf.reaction_states(t.iid, t_react, f.horizon)
                    if not to:
                        rf = None
                    elif cap and budget["react"] >= self.fcfg.react_k:
                        s[n] = capped[n] = True          # past the cap: the reaction is unchecked
                        budget["capped"] += 1
                        continue
                    else:
                        budget["react"] += 1
                        if getattr(f, "v2", False):
                            # v2: the counters from the estimate's templates (forum_v2.RangeSupport.reaction); a
                            # TOOK DAMAGE exit that starts no family has no collider of its own (its next move's
                            # antic comes first)
                            rf = f.rs.reaction(t.iid, to, int(fr[n]), None)
                            self.audit.v2_react += int(rf is not None)
                        else:
                            rf = mf.forecast_reaction(t.iid, to, t_react, f.horizon, f.origin_t)
                    cache[key] = rf
                if rf is not None:
                    by_rf.setdefault(key, []).append(n)
            for key, ns in by_rf.items():
                ns = np.array(ns, np.int64)
                occ[ns] |= self._contacts(cache[key], bnd[ns], tk, skip[ns])     # the reaction moves with the push
                if kbs and moved[ns].any():                                       # ... or not (a wall, a weak push)
                    occ[ns] |= self._contacts(cache[key], rh.bound[ns], tk, skip[ns])
            s = occ.any(axis=1) | capped
        return s, occ, capped

    def _kb_shifts(self, f, sc, rows, T1: int) -> dict:
        """Track A "kb": {row position n: (enemy iid, group key, dx [T1], dy [T1])} for the rows whose first hit pushes
        its enemy (knockback(): by its type, its state now, the slash kind and the facing), the push from the hit frame
        on (0 before it)."""
        mf = getattr(f, "_fc", None)
        trs = getattr(mf, "trackers", None)
        tg = sc["targets"]
        if not trs or not len(tg):
            return {}
        out = {}
        for n, r in enumerate(rows):
            t = tg[int(sc["first_t"][r])]
            tr = trs.get(t.iid)
            if t.hazard or tr is None:
                continue
            j = int(sc["first_f"][r])
            kind, face = int(sc["first_k"][r]), int(sc["first_face"][r])
            if j < 0 or j >= T1:
                continue
            kb = knockback(t.type_key, tr.state, kind, face, T1 - j, self.fcfg.kb_scale)
            if kb is None:
                continue
            dx, dy = np.zeros(T1), np.zeros(T1)
            dx[j:], dy[j:] = kb
            out[n] = (t.iid, (j, kind, face), dx, dy)
        return out

    @staticmethod
    def _note_hit(rows, sh, oh, cp, sc, t_hit, hit_occ, capped_rows, T1) -> None:
        """The hit branch's contact into FORCED_RISK's ranking: its first frame lowers t_hit, its frames join the row's
        (hit_occ); a row the reaction cap left unchecked is in contact from its hit frame on (capped_rows)."""
        for n, i in enumerate(rows):
            i = int(i)
            if cp[n]:
                capped_rows.append(i)
                h = np.zeros(T1, bool)
                h[max(int(sc["first_f"][i]), 1):] = True
            elif sh[n]:
                h = oh[n]
            else:
                hit_occ.pop(i, None)
                continue
            hit_occ[i] = h
            t_hit[i] = min(int(t_hit[i]), int(np.argmax(h)))

    # ---- the escape check (reactive support, ForumConfig.react "escape") ----

    def _threats(self, f, hero: tuple[float, float]) -> list[tuple]:
        """The attacks enemies in play may start (forum.md §22): per enemy whose walk lets it start an attack within
        the forecast (Subject.t_strike) and per family of its type with a strike time (strikes.json: the least commit
        -> first own damage, the p5 for REACT_EXCEPT): (t_strike, family template id, frames from a commit to its
        first damage less the view's latency, its position, velocity and age). The family template (the logged
        instances' union over the time since their start, coarse) is the attack's reach, wind-up body included."""
        from ssbot.combat.multi_forecast import (BODYREACH_KEEP, REACT_EXCEPT, REACT_LATENCY_S, REACT_THROW_FAMS,
                                                 body_only_families, strike_table)
        from ssbot.core.worldstate import ORACLE
        mf = getattr(f, "_fc", None)
        if mf is None or not hasattr(mf, "trackers"):
            return []
        thrown_out = self.fcfg.notstarted and mf.view == ORACLE
        dt = self.params.frame_time
        lat = REACT_LATENCY_S.get(mf.view, 3 * dt)
        cached = getattr(self, "_strike_by_type", None)          # (the config it was built for, by type)
        by_type = cached[1] if cached is not None and cached[0] == self.fcfg.body_reach else None
        if by_type is None:
            by_type = {}
            for (tk, fam), (lo, p5) in strike_table().items():
                by_type.setdefault(tk, []).append((fam, p5 if fam in REACT_EXCEPT else lo))
            br, br_all = self.fcfg.body_reach
            if br:
                # "+b": the body-only families out of the support strike from their commit on (no wind-up)
                for tk, fam in sorted(body_only_families()):
                    if br_all or tk not in BODYREACH_KEEP:
                        by_type.setdefault(tk, []).append((fam, 0.0))
            self._strike_by_type = (self.fcfg.body_reach, by_type)
        reach = getattr(self, "_esc_reach", None)
        if reach is None:
            reach = self._esc_reach = {}
        out = []
        hx, hy = hero
        for s in f.subjects:
            if not s.alive or not s.in_play or not math.isfinite(s.t_strike):
                continue
            tr = mf.trackers.get(s.iid)
            if tr is None or tr.pos is None:
                continue
            for fam, d in by_type.get(s.type_key, ()):
                if fam in ESC_COUNTERS:
                    continue                      # a counter strikes only a hero hitting the guard (the hit branch's)
                if thrown_out and (s.type_key, fam) in REACT_THROW_FAMS:
                    continue                      # "+n", oracle: a throw's pin / bell is on its path once thrown (its
                    #                               family template holds every direction one was thrown: no escape)
                d_f = max((d - lat) / dt, 1.0)
                if d_f + self.fcfg.esc_after_f > ESC_MAX_F:
                    continue                      # a strike this far off is the later ticks' (its wind-up only here)
                ftid = mf.tables.key_id(fam, None, "anchor")
                if ftid is None:
                    continue
                n_on = int(math.ceil(d_f)) + self.fcfg.esc_after_f
                r = reach.get((ftid, n_on))
                if r is None:                     # the family template's farthest cell from its anchor over the check
                    offs, nt, t0 = mf.tables.store.bbox_table(int(ftid))
                    b = mf.tables.store.bb_rows()[offs[0]:offs[0] + min(nt, n_on + 2 + int(round(-t0 / dt)))]
                    b = b[b[:, 0] <= b[:, 2]]
                    r = reach[(ftid, n_on)] = float(np.abs(b).max()) if len(b) else 0.0
                # out of reach even if the hero runs at it over the escape (the dead reckoning included)
                ax = tr.pos[0] + tr.vel[0] * (f.origin_t - tr.seen_T)
                ay = tr.pos[1] + tr.vel[1] * (f.origin_t - tr.seen_T)
                if math.hypot(ax - hx, ay - hy) > r + ESC_NEAR_U:
                    continue
                out.append((float(s.t_strike), int(ftid), d_f, tr.pos, tr.vel, f.origin_t - tr.seen_T, lat,
                            f"{s.type_key}/{fam}"))
        return out

    def _esc_cmds(self, L: int) -> np.ndarray:
        """[7, L] escape commands: stay, run either way, a full jump either way (the tails but the jump in place), a
        dash either way then run."""
        c = getattr(self, "_esc_cache", None)
        if c is not None and c.shape[1] == L:
            return c
        t = cmod.tails(L)
        d = np.zeros((2, L), np.int64)
        d[0], d[1] = kin.B_LEFT, kin.B_RIGHT
        d[:, :3] |= B_DASH
        self._esc_cache = np.ascontiguousarray(np.concatenate([t[[0, 1, 2, 4, 5]], d]))
        return self._esc_cache

    def _escape_fail(self, f, start, hold, full, hold_end, r1, rows: np.ndarray, threats: list
                     ) -> tuple[np.ndarray, list]:
        """[len(rows)] how many (threat, check point) pairs leave the row's hero no escape. Check points: the plan's
        end and its late lock-ins (an attack pressed, a lock or a mode without control entered within a strike's
        delay of the end: inside the horizon the delayed support already checks it against every start). At a check
        point the threat's family template is placed starting then (or up to the latency before), at the enemy's
        position dead-reckoned there, both facings; an escape (_esc_cmds, from the hero's state there, the lock it is
        in played out) must keep the nominal box centre out of it until esc_after_f frames past its first damage."""
        from ssbot.combat.enemy_tables import WinBatch
        params = self.params
        dt = params.frame_time
        store = f._fc.tables.store
        T1 = r1.box.shape[1]
        lc = self.fcfg.light_cone
        dmax = max((t[2] for t in threats), default=0.0)
        L = ESC_MAX_F if lc else int(min(ESC_MAX_F, math.ceil(dmax) + self.fcfg.esc_after_f))
        E = self._esc_cmds(L)
        nE = len(E)
        # "+k": a dash / sprint entered is a lock-in too (forum.md 24.5 item 4: ~30 % of the hits taken with the hero
        # locked at the attack's start came in Air Dash / Sprint Air)
        lock = np.isin(r1.mode[rows], ESC_LOCK_MODES + ((kin.M_DASH, kin.M_SPRINT) if self.fcfg.lock_check else ())) \
            | ((r1.flags[rows] & F_ATTACKING) != 0)
        rise = lock[:, 1:] & ~lock[:, :-1]
        # every lock-in when the not-started attacks are out of the support ("+n"); else the late ones (inside the
        # horizon the delayed support already checks the earlier ones against every start)
        k_min = 1 if self.fcfg.notstarted else T1 - 1 - int(math.ceil(dmax))
        cps = []                                   # (row position, check frame)
        for n in range(len(rows)):
            ks = [int(k) + 1 for k in np.flatnonzero(rise[n]) if k_min <= int(k) + 1 < T1 - 1]
            cps += [(n, k) for k in ks] + [(n, T1 - 1)]
        K = r1.final.shape[0]
        st = np.empty((K, len(cps)))
        hs = [np.empty((len(cps),) + np.asarray(a).shape[1:], np.asarray(a).dtype)
              for a in (hold_end.latched, hold_end.desired, hold_end.pending, hold_end.age)]
        by_k: dict = {}
        for m, (n, k) in enumerate(cps):
            by_k.setdefault(k, []).append(m)
        for k, ms in by_k.items():
            ms = np.array(ms, np.int64)
            rr = rows[[cps[m][0] for m in ms]]
            if k == T1 - 1:
                st[:, ms] = r1.final[:, rr]
                h = hold_end
                src = (np.asarray(h.latched)[rr], np.asarray(h.desired)[rr], np.asarray(h.pending)[rr],
                       np.asarray(h.age)[rr])
            else:
                lat_k, h = hold_filter_jit(full[rr, :k], hold)
                st[:, ms] = kin.rollout(start, lat_k, params, self.terrain, threads=self.cfg.threads).final
                src = (h.latched, h.desired, h.pending, h.age)
            for a, b in zip(hs, src):
                a[ms] = b
        hsr = HoldState(*(np.repeat(a, nE, axis=0) for a in hs))
        lat_e, _ = hold_filter_jit(np.tile(E, (len(cps), 1)), hsr)
        re = kin.rollout(np.repeat(st, nE, axis=1), lat_e, params, self.terrain, threads=self.cfg.threads)
        cx = 0.5 * (re.box[..., 0] + re.box[..., 2])
        cy = 0.5 * (re.box[..., 1] + re.box[..., 3])
        inv = (re.flags & F_INVULN) != 0
        j = np.arange(L + 1)
        tk_rel = j * dt
        t_cp = np.array([k * dt for _, k in cps])
        cp_of = np.repeat(np.arange(len(cps)), nE)
        fail = np.zeros(len(rows), np.int64)
        labels: list = [[] for _ in rows]
        for t_strike, ftid, d_f, pos, vel, age, lat, label in threats:
            app = t_cp >= t_strike - dt                 # the enemy may start it then
            if not app.any():
                continue
            ax = pos[0] + vel[0] * (age + t_cp)
            ay = pos[1] + vel[1] * (age + t_cp)
            last = min(L, int(math.ceil(d_f)) + self.fcfg.esc_after_f)
            x = cx - ax[cp_of][:, None]
            y = cy - ay[cp_of][:, None]
            x[:, last + 1:] = np.nan
            x[:, 0] = np.nan
            x[~app[cp_of]] = np.nan
            W = WinBatch(np.array([ftid, ftid], np.int64), np.array([-lat, -lat]), np.zeros(2), np.zeros(2),
                         np.zeros(2), np.array([1, -1], np.int64))
            occ = store.query_win(W, x, y, tk_rel) & ~inv
            esc = (~occ.any(axis=1)).reshape(len(cps), nE).any(axis=1)
            for m in np.flatnonzero(app & ~esc):
                fail[cps[m][0]] += 1
                labels[cps[m][0]].append(label)
        if lc:
            # the light cone (the person's note of 2026-10-08, forum.md §23): the plan's end must not lie where every
            # escape still meets an attack already under way whose timing is known (the committed fine placements of
            # the families that cannot be clashed, the hazards on their paths, death tails) past the horizon: by
            # simulation over the escapes instead of eroding each frame by the reachable set (the same question for
            # the 7 ways out the escape check has)
            ends = np.array([m for m, (_, k) in enumerate(cps) if k == T1 - 1], np.int64)
            if len(ends):
                sel = (ends[:, None] * nE + np.arange(nE)[None]).ravel()
                tq = (T1 - 1) * dt + tk_rel
                occ = self._light_cone_occ(f, cx[sel], cy[sel], tq) & ~inv[sel]
                occ[:, 0] = False
                esc = (~occ.any(axis=1)).reshape(len(ends), nE).any(axis=1)
                for m in ends[~esc]:
                    fail[cps[m][0]] += 1
                    labels[cps[m][0]].append("light cone")
        return fail, labels

    def _escape_fail_v2(self, f, r1, hold_end, rows: np.ndarray) -> tuple[np.ndarray, list]:
        """v2's escape requirement (forum_v2 module docstring): [len(rows)] 1 when no escape command (_esc_cmds, from
        the row's end state, its lock played out by the kinematics) keeps the nominal box centre out of the escape
        check's danger (RangeSupport.occupied_esc: moves under way and hazards with their margins, idle bodies carried
        with forum_v2.ESC_IDLE_M) for forum_v2.ESC_F frames past the end (invulnerable frames skipped), else 0."""
        params = self.params
        dt = params.frame_time
        T1 = r1.box.shape[1]
        L = forum_v2.ESC_F
        E = self._esc_cmds(L)
        nE = len(E)
        h = hold_end
        hs = [np.repeat(np.asarray(a)[rows], nE, axis=0) for a in (h.latched, h.desired, h.pending, h.age)]
        lat_e, _ = hold_filter_jit(np.tile(E, (len(rows), 1)), HoldState(*hs))
        st = np.repeat(r1.final[:, rows], nE, axis=1)
        re = kin.rollout(st, lat_e, params, self.terrain, threads=self.cfg.threads)
        cx = 0.5 * (re.box[..., 0] + re.box[..., 2])
        cy = 0.5 * (re.box[..., 1] + re.box[..., 3])
        tq = (T1 - 1 + np.arange(L + 1)) * dt
        rs = getattr(f, "rs", None)
        occ = (rs.occupied_esc(cx, cy, tq) if rs is not None and hasattr(rs, "occupied_esc") else
               f.occupied(cx, cy, tq)) & ((re.flags & F_INVULN) == 0)
        sctx = getattr(self, "_sctx", None)
        sp = [] if sctx is None or rs is None else [n for n, r in enumerate(rows) if int(r) in set(sctx.rows.tolist())]
        # the special mode: an escape command from a special row's end (the bounce state) leaves the certified bounce
        # (other keys than the entry's), so it is checked against the full escape support like any row's (review
        # 2026-10-12: it read the special support, M's danger dropped, through the certified window); the row's own
        # continuation (the certified path, tail_ok) counts as its escape below
        occ[:, 0] = False
        ok_e = (~occ.any(axis=1)).reshape(len(rows), nE)
        esc = ok_e.any(axis=1)
        if sp:
            # the row's own continuation (its template past the end: the press, the bounce) clear is an escape
            for n in sp:
                if not esc[n] and bool(sctx.tail_ok[int(np.searchsorted(sctx.rows, int(rows[n])))]):
                    esc[n] = True
                    self.audit.sm_tail_esc += 1
        # the first escape that passed, per row (forum_v2.ESC_TAIL: the chosen row's plan keeps it as its tail)
        first = np.argmax(ok_e, axis=1)
        self._v2_esc_first.update({int(r): int(first[j]) for j, r in enumerate(rows) if esc[j]})
        return (~esc).astype(np.int64), [[] if e else ["v2 end"] for e in esc]

    @staticmethod
    def _v2_locked(r1, rows: np.ndarray) -> np.ndarray:
        """[len(rows), T1] the hero cannot start an escape on that frame: an attack swinging, a lock or a mode
        without control, a dash or a sprint (the pending aims' zones assume a free hero at the decision)."""
        md = r1.mode[rows]
        return np.isin(md, ESC_LOCK_MODES + (kin.M_DASH, kin.M_SPRINT)) | ((r1.flags[rows] & F_ATTACKING) != 0)

    # ---- the Bind's lock ("+k", forum.md 24.5 item 4) ----

    def _bind(self, ws, start, hold, prefix, f, ctx):
        """Planner._bind, and with "+k" and "+n" no attack the escape check holds (not started, so not in the
        support) may start and reach the hero while the Bind locks it (_bind_threatened): 21 masks were taken in
        BindCharge / BindBurst with the attack starting in the Bind (forum.md 24.3)."""
        ok, box = super()._bind(ws, start, hold, prefix, f, ctx)
        if ok and self.fcfg.lock_check and self.fcfg.notstarted:
            hero = (0.0, 0.0) if ws is None or ws.hero is None else (float(ws.hero.pos.v[0]), float(ws.hero.pos.v[1]))
            if self._bind_threatened(f, box, len(prefix), hero):
                self.audit.bind_threat += 1
                return False, box
        return ok, box

    def _bind_threatened(self, f, box: np.ndarray, P: int, hero: tuple[float, float], step: int = 2,
                         free_f: int = 6) -> bool:
        """box [P + T + 1, 4]: the Bind macro's rollout (prefix P frames, then the Bind). True when an escape-check
        threat (_threats) starting at any frame from now to the Bind's end (every `step` frames, from its earliest
        start) puts the hero's box centre in its family template before the hero is free again: the Bind's end
        (P + T_BIND_S + DELTA_B_S) plus free_f frames to get out. Both facings, the enemy dead-reckoned to the
        start (the escape check's placement)."""
        from ssbot.combat.enemy_tables import WinBatch
        mf = getattr(f, "_fc", None)
        if mf is None or not hasattr(mf, "tables"):
            return False
        threats = self._threats(f, hero)
        if not threats:
            return False
        dt = self.params.frame_time
        k_end = min(len(box) - 1, P + int(math.ceil((T_BIND_S + DELTA_B_S) / dt)) + free_f)
        cx = 0.5 * (box[:k_end + 1, 0] + box[:k_end + 1, 2])
        cy = 0.5 * (box[:k_end + 1, 1] + box[:k_end + 1, 3])
        store = mf.tables.store
        ks = np.arange(0, k_end, step)
        L = k_end
        j = np.arange(L + 1)
        idx = ks[:, None] + j[None, :]
        live = idx <= k_end
        idx = np.minimum(idx, k_end)
        for t_strike, ftid, d_f, pos, vel, age, lat, label in threats:
            app = ks * dt >= t_strike - dt
            if not app.any():
                continue
            s_ = ks[app] * dt
            ax = pos[0] + vel[0] * (age + s_)
            ay = pos[1] + vel[1] * (age + s_)
            x = np.where(live[app], cx[idx[app]] - ax[:, None], np.nan)
            y = np.where(live[app], cy[idx[app]] - ay[:, None], np.nan)
            W = WinBatch(np.array([ftid, ftid], np.int64), np.array([-lat, -lat]), np.zeros(2), np.zeros(2),
                         np.zeros(2), np.array([1, -1], np.int64))
            if store.query_win(W, x, y, j * dt).any():
                return True
        return False

    # ---- the aimed pins (pin_aim, forum.md §23.7) ----

    def _pin_threats(self, f, tk: np.ndarray) -> list[tuple]:
        """The Reed throws under way whose pin is not out yet (oracle view): (Reed position, velocity, age of the
        sighting, release times [s from the origin: the walk's Throw entry window inside the horizon, every 2 frames])."""
        from ssbot.combat.multi_forecast import BIN as MBIN, DWELL_SLACK_S, WALK_CAP_S
        from ssbot.core.worldstate import ORACLE
        mf = getattr(f, "_fc", None)
        if mf is None or not hasattr(mf, "trackers") or mf.view != ORACLE:
            return []
        T0 = float(f.origin_t)
        t_end = float(tk[-1])
        dt = self.params.frame_time
        out = []
        for tr in mf.trackers.values():
            c = tr.cur
            if tr.dead or not tr.in_play or tr.pos is None or c is None or (tr.tk, c.family) not in PIN_THROWS:
                continue
            fam = tr.table.families.get(c.family)
            if fam is None or tr.state not in fam.states or tr.state == PIN_RELEASE or tr.t_entry is None:
                continue
            dw = tr.table.dwell.get(tr.state)
            age = T0 - tr.t_entry
            overdue = dw is not None and (age > dw[1] + DWELL_SLACK_S or age + f.horizon + MBIN > WALK_CAP_S)
            cur_nodes, _ = mf.walks.get(tr.table, tr.state, (c.family, c.start), tr.dead, overdue)
            ref = T0 if overdue else tr.t_entry
            for nd in cur_nodes:
                if nd.state != PIN_RELEASE or nd.current:
                    continue
                lo, hi = max(ref + nd.lo - T0, MBIN), ref + nd.hi - T0
                if lo > t_end:
                    continue
                rel = np.arange(lo, min(hi, t_end) + 1e-9, 2 * dt)
                out.append((tr.pos, tr.vel, T0 - tr.seen_T, rel if len(rel) else np.array([lo])))
        return out

    def _pin_contacts(self, pins: list, r1, rows: np.ndarray, tk: np.ndarray, enemy_only: bool) -> np.ndarray:
        """[len(rows)] the first frame a row's nominal box meets a pin thrown at where that row is PIN_AIM_F frames
        before each release time (rays at PIN_SPREAD around it, from PIN_SPAWN_U off the Reed, PIN_SPEED; the
        pin's segment sampled at 5 points, grown by PIN_SKIN), -1: none. The first frames before a release that is
        within the aim lag look at where the hero is now."""
        dt = self.params.frame_time
        box = r1.box[rows]
        cx = 0.5 * (box[..., 0] + box[..., 2])
        cy = 0.5 * (box[..., 1] + box[..., 3])
        T1 = box.shape[1]
        inv = ((r1.flags[rows] & F_INVULN) != 0) if enemy_only else np.zeros(cx.shape, bool)
        hx = 0.5 * float(np.median(box[:, 0, 2] - box[:, 0, 0])) + PIN_SKIN
        hy = 0.5 * float(np.median(box[:, 0, 3] - box[:, 0, 1])) + PIN_SKIN
        first = np.full(len(rows), T1, np.int64)
        seg = np.array([-1.0, -0.5, 0.0, 0.5, 1.0]) * PIN_HALF_U
        if len(rows) and pins and not getattr(self, "_pin_ref", False):
            # (numba; the numpy loop below is the reference, _pin_ref: tests/test_three_layer.py)
            rk, rx_, ry_ = [], [], []
            for pos, vel, age, rel in pins:
                for r in rel:
                    rk.append(int(round(r / dt)))
                    rx_.append(pos[0] + vel[0] * (age + r))
                    ry_.append(pos[1] + vel[1] * (age + r))
            first = pin_contacts_kernel(np.ascontiguousarray(cx), np.ascontiguousarray(cy), np.ascontiguousarray(inv),
                                        hx, hy, np.array(rk, np.int64), np.array(rx_), np.array(ry_), PIN_AIM_F,
                                        np.cos(np.array(PIN_SPREAD)), np.sin(np.array(PIN_SPREAD)), PIN_SPAWN_U,
                                        PIN_SPEED * dt, seg)
            return np.where(first < T1, first, -1)
        for pos, vel, age, rel in pins:
            for r in rel:
                kr = int(round(r / dt))
                if kr >= T1 - 1:
                    continue
                ka = max(kr - PIN_AIM_F, 0)
                rx, ry = pos[0] + vel[0] * (age + r), pos[1] + vel[1] * (age + r)
                ks = np.arange(kr, T1)
                s = PIN_SPEED * (ks - kr) * dt                           # [F]
                for ang in PIN_SPREAD:
                    ax, ay = cx[:, ka] - rx, cy[:, ka] - ry
                    nrm = np.maximum(np.hypot(ax, ay), 1e-6)
                    ca, sa = math.cos(ang), math.sin(ang)
                    ux, uy = (ax * ca - ay * sa) / nrm, (ax * sa + ay * ca) / nrm   # [n]
                    ox, oy = rx + PIN_SPAWN_U * ux, ry + PIN_SPAWN_U * uy
                    px = ox[:, None, None] + ux[:, None, None] * (s[None, :, None] + seg[None, None, :])
                    py = oy[:, None, None] + uy[:, None, None] * (s[None, :, None] + seg[None, None, :])
                    hit = ((np.abs(px - cx[:, ks, None]) <= hx) & (np.abs(py - cy[:, ks, None]) <= hy)).any(axis=2)
                    hit &= ~inv[:, ks]
                    k1 = np.where(hit.any(axis=1), ks[hit.argmax(axis=1)], T1)
                    first = np.minimum(first, k1)
        return np.where(first < T1, first, -1)

    def _light_cone_occ(self, f, x: np.ndarray, y: np.ndarray, tq: np.ndarray) -> np.ndarray:
        """The must-escape layer with a known timing at the points x, y [n, T] at tq [T] (s from the origin): the
        committed fine placements of the families clash.json does not clash, the hazards on deterministic paths and
        the death tails (no window placement: its timing is not known, the person's note)."""
        if not hasattr(f, "pm"):
            return np.zeros(np.shape(x), bool)
        fams = getattr(self, "_lc_fams", None)
        if fams is None:
            tab = self.clash_tab if self.clash_tab is not None else ClashTable.load()
            fams = self._lc_fams = frozenset(fam for _, fam in tab.families())
        pm = f.pm
        sel = None
        if len(pm["owner"]):
            sel = pm["committed"] & ~np.array([str(fm) in fams for fm in pm["family"]], bool)
        out = f._fine_occ(x, y, tq, sel) if sel is not None and sel.any() else np.zeros(np.shape(x), bool)
        out |= f._path_occ(x, y, tq)
        out |= f._box_occ(x, y, tq, kinds=("death",))
        return out

    def _escape_pick(self, f, start, hold, full, hold_end, r1, ranked: np.ndarray, hero: tuple[float, float],
                     k: int | None = None, t_end: float | None = None, v2: bool = False
                     ) -> tuple[int | None, int, int, int, list]:
        """Of the first k (default esc_k) rows of `ranked`, the first that passes the escape check, else the one with
        the fewest failures (the first of them). No batch starts that would end past t_end (perf_counter s; a batch
        is taken to cost what the last ones did): self.esc_cut. Returns (row or None: no threats / rows / time, its
        failures, rows checked, threats, its failing threats). v2: the check is _escape_fail_v2 (one threat: the
        estimate past the row's end)."""
        self.esc_cut = False
        threats = [("v2",)] if v2 else self._threats(f, hero)
        if (not threats and not self.fcfg.light_cone) or not len(ranked):
            return None, 0, 0, len(threats), []
        best, best_fail, checked, best_lab = None, 0, 0, []
        K = min(self.fcfg.esc_k if k is None else k, len(ranked))
        c_start = 0
        cache = getattr(self, "_hf_esc", None) if v2 else None
        if cache:
            # review2: the leading rows of the order already checked (HITS_FIRST's tiers): their results, in order
            for r in ranked[:K]:
                if int(r) not in cache:
                    break
                n, lb, e1 = cache[int(r)]
                c_start += 1
                checked += 1
                self.audit.hf_esc_reused += 1
                if n == 0:
                    if e1 is not None:
                        self._v2_esc_first[int(r)] = e1       # (forum_v2.ESC_TAIL's escape for the row)
                    return int(r), 0, checked, len(threats), []
                if best is None or n < best_fail:
                    best, best_fail, best_lab = int(r), int(n), lb
        for c0 in range(c_start, K, ESC_CHUNK):
            tc = time.perf_counter()
            if t_end is not None and tc + self.esc_batch_s > t_end:
                self.esc_cut = True
                break
            rows = np.asarray(ranked[c0:min(K, c0 + ESC_CHUNK)], np.int64)
            if v2:
                nf, lab = self._escape_fail_v2(f, r1, hold_end, rows)
                self.audit.v2_esc_rows += len(rows)
            else:
                nf, lab = self._escape_fail(f, start, hold, full, hold_end, r1, rows, threats)
            self.esc_batch_s = 0.5 * self.esc_batch_s + 0.5 * (time.perf_counter() - tc)
            checked += len(rows)
            for r, n, lb in zip(rows, nf, lab):
                if n == 0:
                    return int(r), 0, checked, len(threats), []
                if best is None or n < best_fail:
                    best, best_fail, best_lab = int(r), int(n), lb
        rs = getattr(f, "rs", None)
        if v2 and forum_v2.ESC_MORE > 0 and len(ranked) > K and not self.esc_cut and rs is not None:
            # v2: none of the first K had an escape - look further down the order, the rows whose end stays clear
            # of the escape danger for a while first (a retreat; 1v1 live: the top rows all approached the Clapper)
            rest = np.asarray(ranked[K:], np.int64)
            end = r1.box[rest, -1, :]
            ex = np.repeat((0.5 * (end[:, 0] + end[:, 2]))[:, None], 4, axis=1)
            ey = np.repeat((0.5 * (end[:, 1] + end[:, 3]))[:, None], 4, axis=1)
            tq = np.broadcast_to((r1.box.shape[1] - 1 + np.array([6, 12, 18, 24])) * self.params.frame_time,
                                 ex.shape)
            clear = ~rs.occupied_esc(ex, ey, tq).any(axis=1)
            rest = np.concatenate([rest[clear], rest[~clear]])[:forum_v2.ESC_MORE]
            for c0 in range(0, len(rest), ESC_CHUNK):
                tc = time.perf_counter()
                if t_end is not None and tc + self.esc_batch_s > t_end:
                    self.esc_cut = True
                    break
                rows = rest[c0:c0 + ESC_CHUNK]
                nf, lab = self._escape_fail_v2(f, r1, hold_end, rows)
                self.audit.v2_esc_rows += len(rows)
                self.audit.v2_esc_more += len(rows)
                self.esc_batch_s = 0.5 * self.esc_batch_s + 0.5 * (time.perf_counter() - tc)
                checked += len(rows)
                for r, n in zip(rows, nf):
                    if n == 0:
                        return int(r), 0, checked, len(threats), []
        return best, best_fail, checked, len(threats), best_lab

    def _contacts_fn(self, f, bound: np.ndarray, tk: np.ndarray, skip: np.ndarray, occ_fn) -> np.ndarray | None:
        """Planner._contacts against occ_fn(X, Y) (an occupancy of the hull points [n, T1]; None: not applicable)."""
        hx, hy = f.fc.half
        X, Y, rows, too_wide = _hull_points(np.ascontiguousarray(bound), hx, hy, self.cfg.max_points)
        hit = occ_fn(X, Y)
        if hit is None:
            return None
        N = bound.shape[0]
        occ = hit[:N].copy()
        if len(rows):
            occ[rows] |= hit[N:].reshape(-1, len(rows), hit.shape[1]).any(axis=0)
        occ |= too_wide
        occ &= ~skip
        occ[:, 0] = False
        return occ

    def _contacts_only(self, f, bound: np.ndarray, tk: np.ndarray, skip: np.ndarray, iids) -> np.ndarray:
        """Planner._contacts against the support of the enemies `iids` only."""
        hx, hy = f.fc.half
        X, Y, rows, too_wide = _hull_points(np.ascontiguousarray(bound), hx, hy, self.cfg.max_points)
        hit = f.occupied_only(X, Y, tk, list(iids))
        N = bound.shape[0]
        occ = hit[:N].copy()
        if len(rows):
            occ[rows] |= hit[N:].reshape(-1, len(rows), hit.shape[1]).any(axis=0)
        occ |= too_wide
        occ &= ~skip
        occ[:, 0] = False
        return occ

    def _clash_contacts(self, f, bound: np.ndarray, tk: np.ndarray, skip: np.ndarray, stops: list) -> np.ndarray:
        """The clash branch's contact [n, T1]: rows without a stopped enemy as _contacts; a row whose clash ended a
        PARRIED-catching attack (stops[q] = {iid: (clash frame j, type key)}) meets the support without those enemies
        plus each one's support as it is up to j and frozen at j for PARRY_STOP_F frames, the hull grown there by what
        the enemy still moves (stop_grow)."""
        occ = np.zeros(bound.shape[:2], bool)
        plain = [q for q, st in enumerate(stops) if not st]
        if plain:
            occ[plain] = self._contacts(f, bound[plain], tk, skip[plain])
        groups: dict = {}
        for q, st in enumerate(stops):
            if st:
                groups.setdefault(tuple(sorted(st.items())), []).append(q)
        for items, qs in groups.items():
            qs = np.array(qs, np.int64)
            o = self._contacts(f, bound[qs], tk, skip[qs], exclude={iid for iid, _ in items})
            for iid, (j, tkn) in items:
                tk2 = np.array(tk, np.float64, copy=True)
                tk2[j:j + PARRY_STOP_F] = tk[min(j, len(tk) - 1)]
                gx, gy = stop_grow(tkn, np.arange(bound.shape[1] - j))
                b2 = bound[qs].copy()
                b2[:, j:, 0] -= gx
                b2[:, j:, 2] += gx
                b2[:, j:, 1] -= gy
                b2[:, j:, 3] += gy
                o |= self._contacts_only(f, b2, tk2, skip[qs], [iid])
            occ[qs] = o
        return occ

    def _reach_first(self, f, bound: np.ndarray, tk: np.ndarray, k0: int, j_hi: int, kind: int, face: int,
                     iids) -> int:
        """The earliest frame in [k0, j_hi] on which the swing's clash reach (placed on the hull's centres) can meet
        the support of the enemies iids (a lower bound of the clash frame: the support holds the body too); j_hi
        when it cannot before."""
        if j_hi <= k0:
            return j_hi
        x0, x1, y0, y1 = self.reach[kind]
        fx0, fx1 = sorted((face * x0, face * x1))
        hx, hy = f.fc.half
        ks = np.arange(k0 - 1, j_hi + 1)             # one frame before: _contacts_only clears its first frame
        b = bound[ks]
        cx0, cx1 = b[:, 0] + hx, b[:, 2] - hx
        cy0, cy1 = b[:, 1] + hy, b[:, 3] - hy
        mx, my = 0.5 * (cx0 + cx1), 0.5 * (cy0 + cy1)
        cx0, cx1 = np.minimum(cx0, mx), np.maximum(cx1, mx)
        cy0, cy1 = np.minimum(cy0, my), np.maximum(cy1, my)
        rb = np.stack([cx0 + fx0, cy0 + y0, cx1 + fx1, cy1 + y1], axis=1)[None]
        o = self._contacts_only(f, rb, np.ascontiguousarray(tk[ks]), np.zeros(rb.shape[:2], bool), list(iids))[0]
        o[0] = False
        return int(ks[int(np.argmax(o))]) if o.any() else j_hi

    def _owner_rule(self, owners, kind: int, face: int, cx: float, cy: float, ta: float, tb: float, cw: dict
                    ) -> tuple[list, list, bool]:
        """The enemies in contact at a planned clash (owners: their trackers): (rates [(p_fail, p_clash_lb)] and
        clashed [(tracker, stop)] of those whose current family the table clashes with this slot, on the slash's side
        (side: in front of the facing, up: above, down: below), that may be in a clashable state in [ta, tb] (cw: their
        clash_windows), others: a committed co-owner that cannot be clashed there (another family, outside its
        clashable states, behind the slash)). The clash needs one such clashable attack; the co-owners do not block it:
        the parry i-frames take every enemy's damage (the two-sided rule), the branch meets their support with those
        frames masked, and its contact after them stays in the branch (partial) or is clashed on the next level; a clash
        that does not happen leaves the plain row (FORCED_RISK's mixture)."""
        rates, clashed, others = [], [], 0
        for tr in owners:
            fam = tr.cur.family if tr.cur is not None and tr.cur.t_end is None else None
            rt = self.clash_tab.rate(tr.tk, fam, KIND_SLOT[kind], self.crest)
            dx, dy = tr.pos[0] - cx, tr.pos[1] - cy
            side_ok = (kind == K_SIDE and dx * face >= 0) or (kind == K_UP and dy > 0) or \
                (kind == K_DOWN and dy < 0) or kind == K_WALL
            spans = [w for w in cw.get(tr.iid, ()) if w[0] <= tb and w[1] >= ta]
            if rt is not None and side_ok and spans:
                rates.append(rt)
                clashed.append((tr, all(w[2] for w in spans)))
            elif fam is not None and fam != tr.table.spec.idle_family:
                others += 1
                self.audit.clash_off_state += int(rt is not None and side_ok)
        return rates, clashed, others

    def clash_allowed(self, ctx) -> bool:
        """The clash pass's tier gate: never with a pause pending; a tier of clash_tiers (DESIGN 3.5.6: GREEN), or
        with clash_main (the three-layer support, forum.md §23) a YELLOW at h >= clash_main_h too (the YELLOW of the
        last plan's S = 1: a clash row is the way back to GREEN; h 2 and RED stay out); any tier when the supervisor
        is in its free mode (FilterContext.free: the DESIGN 3.5.6 revision of 2026-10-08, h >= 2)."""
        if getattr(ctx, "pause_pending", False):
            return False
        if getattr(ctx, "free", False):
            return True                      # the DESIGN 3.5.6 revision (2026-10-08): h >= 2, anything goes until hit
        tier = getattr(ctx, "tier", GREEN)
        if tier in self.fcfg.clash_tiers:
            return True
        h = getattr(ctx, "h", None)
        return bool(self.fcfg.clash_main and tier == YELLOW and h is not None and h >= self.fcfg.clash_main_h)

    def _clash_pass(self, f, start, latched, sc, S, ok, hz, tk, enemy_only, ctx, t_hit, t0: float) -> dict:
        """EV_CLASH (forum_planner_plan R8): for up to clash_k rows in contact the clash branch (the latest first
        contact first, then the row index: never J, so whether a tick ends in FORCED_RISK does not depend on the prefs,
        Â§4.4 item 2). Only in the tiers clash_tiers (DESIGN 3.5.6: GREEN), never with a pause pending, with h >=
        clash_min_h. A row's first contact (the envelope) must fall in a swing's active window (crest table: the clash
        frame below inside [k_s + f0, k_s + f1], the frames the kernel scores) and come from an enemy whose current
        attack family can be clashed with that slot (ClashTable) and that may be in one of the family's clashable
        Control states at the clash (clash_windows: a contact from its antic body or its recovery is not clashable),
        on the slash's side of the hero (side: in front of the facing, up: above, down: below); other enemies in
        contact there do not block it (_owner_rule: the parry i-frames take their damage too). The clash is put on the frame before the contact (the clash reach lies outside the hurtbox) or the window's first
        frame (j_hi); the reach can meet the support from j_lo (_reach_first) on, so the parry i-frames (no enemy
        damage: parryInvulnTimer covers every ENEMY hazard, the two-sided rule) are the frames covered whichever frame
        in [j_lo, j_hi] the clash takes: [j_hi, j_lo + PARRY_INVULN_F). The direction's recoil (side: away from the
        facing, up: RecoilDown, down: the bounce; a wall slash none) and the attack reset PARRY_RECOVER_F frames later
        (EV_PARRY_RECOVER: the next swing may come at once) on j_hi; its next contact may be clashed again (a later
        segment of a multi-hit attack, the other side) up to clash_depth times; a clash in a PARRIED-catching state
        (PARRY_STOPS: the Envoy's charge, the Reed's counter) ends that attack (_clash_contacts). The deadline: no level
        starts that would end past clash_deadline_ms (it costs about what the last one did). Returns {row: (w, p_hit,
        clashes, first contact left (T1: clean), the branch's contact [T1] or None when clean)} for rows with at least
        one clash and w >= clash_partial_min_p, w = prod(p_clash_lb) (every clash happens), p_hit = 1 - prod(1 -
        p_fail)."""
        fcfg = self.fcfg
        au = self.audit
        mf = getattr(f, "_fc", None)
        h = getattr(ctx, "h", None)
        if mf is None or self.clash_tab is None or not fcfg.clash_branch or not hasattr(mf, "trackers") or \
                (h is not None and h < fcfg.clash_min_h):
            return {}
        if not self.clash_allowed(ctx):
            au.clash_tier_skip += 1
            return {}
        cand = np.flatnonzero(ok & ~hz & S & (sc["sw_f"] >= 1))
        if not len(cand):
            return {}
        T = latched.shape[1]
        T1 = T + 1
        T0 = float(f.origin_t)
        hor = float(tk[-1]) + float(tk[1] - tk[0])
        fr_s = float(tk[1] - tk[0])
        # only enemies in an attack of their own can own a contact that matters here (an idle one never stops a clash,
        # see the attribution below); the clashable spans of those in a clashable family: without one in the horizon
        # no row can clash
        trs = {iid: tr for iid, tr in mf.trackers.items() if tr.in_play and not tr.dead and tr.pos is not None
               and tr.cur is not None and tr.cur.t_end is None and tr.cur.family != tr.table.spec.idle_family}
        cw: dict = {}
        for iid, tr in trs.items():
            if (tr.tk, tr.cur.family) not in self.clash_fams:
                continue
            cs_ = self.clash_tab.clash_states(tr.tk, tr.cur.family)
            if cs_ is None:
                w_ = [(-math.inf, math.inf, False)]
            else:
                w_ = clash_windows(tr.table, tr.cur.family, tr.state, tr.t_entry, T0, cs_,
                                   frozenset(s for t2, s in PARRY_STOPS if t2 == tr.tk), hor)
            w_ = [x for x in w_ if x[1] >= T0 and x[0] <= T0 + hor]
            if w_:
                cw[iid] = w_
        if not cw:
            return {}
        deadline = fcfg.clash_deadline_ms if fcfg.clash_deadline_ms is not None else fcfg.deadline_ms + 2.0
        if (time.perf_counter() - t0) * 1e3 + self._clash_lvl_ms > deadline:
            au.clash_cut += 1
            return {}
        # rows whose first swing is out at their first contact first (the nominal lane's swing, the contact's
        # estimate), then the latest first contact, then the row index
        win = self.shapes[3]
        si = np.clip(sc["sw_k"][cand] - 1, 0, len(win) - 1)
        k_on, th = sc["sw_f"][cand] + win[si, 0], t_hit[cand]
        inw = (k_on <= th) & (np.maximum(th - 1, k_on) < sc["sw_f"][cand] + win[si, 1])
        cand = cand[np.lexsort((cand, -th, ~inw))][:fcfg.clash_k]
        n = len(cand)
        au.clash_cand += n
        lat = np.ascontiguousarray(latched[cand])
        slot_i = {K_SIDE: 0, K_UP: 1, K_WALL: 2, K_DOWN: 3}
        face0 = 1 if np.asarray(start).reshape(kin.K, -1)[kin.FACE, 0] >= 0 else -1
        ev = np.zeros((n, T), np.int64)
        inv = np.zeros((n, T1), bool)
        w_ok = np.ones(n)                            # prod p_clash_lb: every clash so far happens
        h_ok = np.ones(n)                            # prod (1 - p_fail)
        ncl = np.zeros(n, np.int64)
        alive = np.ones(n, bool)
        last_cl = np.full(n, -100, np.int64)
        stops: list[dict] = [{} for _ in range(n)]
        cfams: list[set] = [set() for _ in range(n)]   # (type, family) each row's clashes meet (track A "whip")
        part: dict[int, tuple] = {}                  # row m -> (first contact, contact [T1]) after its clashes so far
        out = {}
        for depth in range(fcfg.clash_depth + 1):
            idx = np.flatnonzero(alive)
            if not len(idx):
                break
            tl = time.perf_counter()
            r2 = kin.rollout(start, lat[idx], self.params, self.terrain, events=ev[idx], variants=fcfg.variants,
                             threads=self.cfg.threads)
            skip = ((r2.flags_all & F_INVULN) != 0) if enemy_only else np.zeros(r2.flags_all.shape, bool)
            occ = self._clash_contacts(f, r2.bound, tk, skip | inv[idx], [stops[m] for m in idx])
            hit = occ.any(axis=1)
            for q, m in enumerate(idx):
                if not hit[q]:
                    alive[m] = False
                    if ncl[m] > 0:
                        out[int(cand[m])] = (float(w_ok[m]), 1.0 - float(h_ok[m]), int(ncl[m]), T1, None)
                elif ncl[m] > 0:
                    part[m] = (int(np.argmax(occ[q])), occ[q].copy())
            lvl_ms = (time.perf_counter() - tl) * 1e3
            if depth == 0:
                self._clash_lvl_ms = 0.8 * self._clash_lvl_ms + 0.2 * lvl_ms
            if depth == fcfg.clash_depth:
                break
            if (time.perf_counter() - t0) * 1e3 + lvl_ms > deadline:
                au.clash_cut += 1
                break
            # the swing out at each pending row's first contact
            plan = []                                # (m, q, t_c, j_hi, k_on, kind, face, cx, cy)
            for q, m in enumerate(idx):
                if not hit[q]:
                    continue
                t_c = int(np.argmax(occ[q]))
                got = None
                for k_s, kind, face in swings(r2.flags[q], r2.mode[q], lat[m], r2.box[q], face0, self.down_slash):
                    a, b = int(win[slot_i[kind], 0]), int(win[slot_i[kind], 1])     # active frames [k_s + a, k_s + b)
                    j = max(t_c - 1, k_s + a)
                    if k_s + a >= 1 and k_s + a <= t_c and j < k_s + b:
                        got = (j, kind, face, k_s + a)
                if got is None or got[0] <= last_cl[m]:
                    alive[m] = False
                    continue
                au.clash_inwin += 1
                bx = r2.bound[q, t_c]
                plan.append((m, q, t_c, got[0], got[3], got[1], got[2], 0.5 * (bx[0] + bx[2]),
                             0.5 * (bx[1] + bx[3])))
            if not plan:
                break
            # who is in contact at t_c (each enemy's own support at the hull centre), grouped by contact frame
            owners: dict[int, list] = {e[0]: [] for e in plan}
            by_t: dict[int, list] = {}
            for e in plan:
                by_t.setdefault(e[2], []).append(e)
            for t_c, es in by_t.items():
                X = np.array([[e[7]] for e in es])
                Y = np.array([[e[8]] for e in es])
                tt = tk[t_c:t_c + 1]
                for iid, tr in trs.items():
                    if not any(abs(tr.pos[0] - e[7]) < 12.0 and abs(tr.pos[1] - e[8]) < 12.0 for e in es):
                        continue
                    o = f.occupied_only(X, Y, tt, [iid])[:, 0]
                    for e, hit_e in zip(es, o):
                        if hit_e:
                            owners[e[0]].append(tr)
            for m, q, t_c, j_hi, k_on, kind, face, cx, cy in plan:
                rates, clashed, others = self._owner_rule(owners[m], kind, face, cx, cy,
                                                          T0 + float(tk[j_hi]) - fr_s, T0 + float(tk[t_c]) + fr_s, cw)
                au.clash_owned += int(bool(owners[m]))
                au.clash_coowned += int(bool(rates) and others > 0)
                if not rates:
                    alive[m] = False
                    continue
                au.clash_known += 1
                w_new = w_ok[m] * min(r[1] for r in rates)
                if w_new < fcfg.clash_partial_min_p:
                    alive[m] = False                 # too unlikely to rank on: the branch so far stays (part)
                    continue
                for tr, stop in clashed:
                    cfams[m].add((tr.tk, tr.cur.family if tr.cur is not None else None))
                    if stop:
                        stops[m].setdefault(tr.iid, (j_hi, tr.tk))
                        au.clash_stops += 1
                j_lo = self._reach_first(f, r2.bound[q], tk, k_on, j_hi, kind, face, [tr.iid for tr, _ in clashed])
                w_ok[m] = w_new
                h_ok[m] *= 1.0 - max(r[0] for r in rates)
                ncl[m] += 1
                last_cl[m] = j_hi
                bit = kin.EV_POGO if kind == K_DOWN else kin.EV_RECOIL_DOWN if kind == K_UP else \
                    0 if kind == K_WALL else (kin.EV_RECOIL_L if face > 0 else kin.EV_RECOIL_R)
                if j_hi < T:
                    ev[m, j_hi] |= bit
                if j_hi + PARRY_RECOVER_F < T:
                    ev[m, j_hi + PARRY_RECOVER_F] |= kin.EV_PARRY_RECOVER
                inv[m, j_hi:max(j_hi, j_lo + PARRY_INVULN_F)] = True
        for m, (tn, oc) in part.items():
            out.setdefault(int(cand[m]), (float(w_ok[m]), 1.0 - float(h_ok[m]), int(ncl[m]), tn, oc))
        # the branch's parry i-frames per row (clash_main: FORCED_RISK's seen keys skip them, R8's open note: the
        # collider a swing clashes is no contact of that row)
        self._clash_inv = {int(cand[m]): inv[m].copy() for m in range(n) if int(cand[m]) in out}
        self._clash_fams = {int(cand[m]): frozenset(cfams[m]) for m in range(n) if int(cand[m]) in out}
        return {i: v for i, v in out.items() if v[0] >= fcfg.clash_partial_min_p}

    @staticmethod
    def _s1_frames(T1: int) -> np.ndarray:
        """Stage 1's frames: 1-3 each, then every other one, and the last."""
        return np.unique(np.concatenate([np.arange(1, min(4, T1)), np.arange(5, T1, 2), [T1 - 1]])).astype(np.int64)

    # ---- the tick ----

    @staticmethod
    def _clapper_near(f, start: np.ndarray) -> bool:
        """SSBOT_FORUM_CL_NODOWN: a tracked Clapper (Song Heavy Sentry) within CL_NODOWN_U of the hero in x."""
        trk = getattr(getattr(f, "rs", None), "trk", None)
        if trk is None:
            return False
        hx_ = float(np.asarray(start).reshape(kin.K, -1)[kin.PX, 0])
        for _iid, (tk, e, _inst) in trk.now.items():
            p = e.get("pos")
            if (e.get("type_key") or tk) == "Song Heavy Sentry" and p and abs(float(p[0]) - hx_) <= CL_NODOWN_U:
                return True
        return False

    def _special_rows(self, f, start: np.ndarray, prefix: np.ndarray, T: int):
        """The special-move table's arrive-and-strike rows (combat.specials, SSBOT_FORUM_SPECIALS=1; forum.md 48):
        for the nearest enemy in a move the table knows, within reach (12 u), the rows that put the hero in one of
        the move's entries (the press frame still ahead) and press there. The normal checks then judge them like any
        row. Costs kept in self.spec_ms / self.spec_n (last_info["spec"])."""
        rs = getattr(f, "rs", None)
        trk = getattr(rs, "trk", None)
        if trk is None:
            return None
        if not hasattr(self, "_spec_tab"):
            from ssbot.combat.pogo_slam import SlamTimeline
            # SSBOT_FORUM_SPECIAL_TABLE=v2 (G4): the merged table (the slack cores) in the special mode
            self._spec_tab = specials.SpecialTable.load(suffix="_v2") if (special_mode.SPECIAL_MODE and
                                                                           special_mode.TABLE == "v2")                 else specials.SpecialTable.load()
            self._spec_disp = SlamTimeline.load().disp
        hx_ = float(np.asarray(start).reshape(kin.K, -1)[kin.PX, 0])
        best = None
        for iid, (tk, e, _inst) in trk.now.items():
            p = e.get("pos")
            mv = specials.enemy_move({"type_key": e.get("type_key") or tk, "fsms": e.get("fsms")})
            if mv is None or not p or abs(float(p[0]) - hx_) > 12.0:
                continue
            if special_mode.SPECIAL_MODE and not special_mode.in_family(mv[0], _inst):
                # review 2026-10-12: the jump and the jump cast land through the same Control states (Slam 2, Slam
                # Recover) as the slam: only the tracked instance of the table's own family is that move
                continue
            if best is None or abs(float(p[0]) - hx_) < best[0]:
                best = (abs(float(p[0]) - hx_), e, mv, iid, tk)
        if best is None:
            return None
        _, e, (move, k_now), iid_, tk_ = best
        mode = special_mode.SPECIAL_MODE
        k_trk = k_now
        if mode:
            # the special mode: the mode's certs (both + bounce: a down slash on an enemy in a move is a certain hit),
            # the tracker's look-ahead shift (move frame at the planner's rollout index 0), long rows
            k_now = k_trk - int(getattr(rs, "k_shift", 0) or 0)
        lut = self._spec_tab.lut(move, special_mode.MODE_CERTS, rank_cert=False) if mode else self._spec_tab.lut(move)
        if lut is None or k_now + specials.REACT_F >= lut.K:
            return None
        t0 = time.perf_counter()
        face = 1 if e.get("flipX") else -1
        disp = self._spec_disp
        xa = float(e["pos"][0]) - face * disp[min(max(k_trk, 0), len(disp) - 1)]
        full_tick = True
        if mode and special_mode.FAST:
            # G3 item 3: the whole set every FULL_EVERY ticks and on the move's first tick, else the rows that start now
            c_ = getattr(self, "_sm_full", None)
            full_tick = c_ is None or c_["iid"] != int(iid_) or c_["move"] != move or \
                self.ticks - c_["tick"] >= special_mode.FULL_EVERY
            if full_tick:
                self._sm_full = {"iid": int(iid_), "move": move, "tick": self.ticks, "board": None}
            self.audit.sm_full_ticks += int(full_tick)
        pk = getattr(self, "_pv_sm_now", None)
        if mode and special_mode.KEEP and getattr(self, "_kp", None) == "sm" and pk is not None and                 pk.get("iid") == int(iid_) and pk.get("move", move) == move:
            # SSBOT_FORUM_SPECIAL_KEEP (G4 4b): a kept special row: no template search this tick (its CONTINUE is
            # re-certified and checked as a special row; the normal set stays the fallback)
            r = specials.StrikeRows(np.zeros((0, int(T)), np.int64), [], np.zeros(0, np.int64), 0, [])
            self.audit.kp_skip += 1
        else:
            r = specials.strike_rows(self.params, self.terrain, start, lut, k_now, xa, float(e["pos"][1]), face, disp,
                                     T, threads=self.cfg.threads, prefix=prefix,
                                     **({"long_hi": special_mode.LONG_PRESS_MAX if special_mode.LONG else None,
                                         "early_first": True, "max_rows": special_mode.MAX_ROWS} if mode else {}),
                                     **({"now_only": True} if not full_tick else {}),
                                     **({"hold_rem": max(int(self.jump_until - self.ticks), 0)}
                                        if mode and special_mode.HOLD else {}))
        self.spec_ms = (time.perf_counter() - t0) * 1e3
        self.spec_n = (len(r.cmd), r.tried)
        if mode:
            self._spec_meta = {"iid": int(iid_), "tk": tk_, "move": move, "k_trk": int(k_trk), "k0": int(k_now),
                               "xa": xa, "cy": float(e["pos"][1]), "face": face, "lut": lut}
        return r

    HOP_SRC = ("ATTACK(side)N+clashrepN", "WAIT+clashrepN")
    HOP_HOLD = 11                 # the hop: jump held 11 frames (the set's JUMP(11)), one press

    def _sm_board(self, iid: int, move: str, k0: int, on: bool, x) -> None:
        """SSBOT_FORUM_SPECIAL_FAST: a full tick's BOARD decision is cached; a tick between full ones without a safe
        special row of its own posts the cached strike spot while its press is still ahead (the L2 keeps walking
        there; the rows that start now find the strike once it is in reach)."""
        c_ = getattr(self, "_sm_full", None)
        if c_ is None or c_["iid"] != int(iid) or c_["move"] != move:
            return
        if c_["tick"] == self.ticks:
            c_["board"] = {"on": bool(on), "x": x, "k0": int(k0)} if on else None
            return
        b_ = c_.get("board")
        if on or b_ is None:
            return
        special_mode.BOARD[int(iid)] = {"tick": self.ticks, "move": move, "k": int(k0), "on": True, "x": b_["x"],
                                        "rows": 0, "safe": 0, "cached": True}
        self.audit.sm_board_cached += 1

    def _rune_hop_rows(self, f, start, hold, prefix: np.ndarray, T: int):
        """SSBOT_FORUM_RUNE_HOP (task 1v1 G2; the person: continuous slashes on the ground and one short hop just
        before the bomb at the hero lights, no second jump press in the air): the set's ground slash / wait rows
        with one JUMP(11) press timed from the per-bomb forecast (forum_v2 RangeSupport.bombs_all). The hop's clear
        frames (no overlap with that bomb's circle, BOMB_M margin) come from a probe rollout pressed at once; the
        press puts the bomb's lit window inside them (+-2 frames). (cmd [n, T], names, prim bits) or None."""
        rs = getattr(f, "rs", None)
        bk = getattr(rs, "bombs_all", None)
        if bk is None or not len(bk):
            return None
        cs = self.fsets["ground"][0]
        if not hasattr(self, "_hop_src"):
            nm = [cs.name(i) for i in range(len(cs.cmd))]
            self._hop_src = [nm.index(n) for n in self.HOP_SRC if n in nm]
        src = self._hop_src
        if not src:
            return None
        st = np.asarray(start).reshape(kin.K, -1)
        hx = float(st[kin.PX, 0])
        P = len(prefix)
        ks = int(getattr(rs, "k_shift", 0) or 0)
        near = np.abs(bk[:, 1] - hx) < bk[:, 3] + rune_bombs.HB_HX + 0.5
        near &= bk[:, 4] + ks - P >= 2                     # lights after the row's first frames
        if not near.any():
            return None
        b = bk[np.flatnonzero(near)[np.argmin(bk[near, 4])]]
        on_p, off_p = int(b[4]) + ks, int(b[5]) + ks          # planner frames
        H = self.HOP_HOLD
        probe = cs.cmd[src[:1]].copy()
        probe[:, :H] |= B_JUMP
        full = np.concatenate([np.broadcast_to(np.asarray(prefix, np.int64), (1, P)), probe], axis=1)
        lat, _ = hold_filter_jit(full, hold)
        rp = kin.rollout(start, lat, self.params, self.terrain, threads=1)
        bx_ = rp.box[0]
        cx = 0.5 * (bx_[:, 0] + bx_[:, 2])
        cy = 0.5 * (bx_[:, 1] + bx_[:, 3])
        geo = b[None, :].copy()
        geo[0, 4], geo[0, 5] = -1e9, 1e9                    # the circle at every frame: where the hop clears it
        hit = rune_bombs.occupied(geo, cx, cy, np.zeros(len(cx)), rune_bombs.BOMB_M)
        rel = np.flatnonzero(~hit[P + 1:])                  # clear frames after the press (index 0 = press frame)
        if not len(rel):
            return None
        # the longest run of clear frames that starts after the take-off
        runs = np.split(rel, np.flatnonzero(np.diff(rel) > 1) + 1)
        runs = [r_ for r_ in runs if r_[0] > 0] or runs
        best = max(runs, key=len)
        a, z = int(best[0]), int(best[-1])
        lo, hi = off_p - (P + 1) - z, on_p - (P + 1) - a       # press cmd index c with [on, off] inside [c + a, c + z]
        c0 = (lo + hi) // 2 if lo <= hi else int(round(0.5 * (on_p + off_p) - (P + 1) - 0.5 * (a + z)))
        cs_ = sorted({c for c in (c0 - 2, c0, c0 + 2) if 0 <= c <= T - H})
        if not cs_:
            return None
        cmd, names, bits, cq = [], [], [], []
        jb = 1 << 1                                         # Prim.JUMP
        for i in src:
            for c in cs_:
                m = cs.cmd[i].copy()
                m[c:c + H] |= B_JUMP
                cmd.append(m)
                names.append(f"{cs.name(i)}_hop{c}")
                bits.append(int(cs.prim_bits[i]) | jb)
                cq.append(c)
        # review 2026-10-12: the row's press must be a jump from the ground in the model (the person: no second jump
        # press in the air). A jump in flight (the prefix's, or one the held key starts) would make it a second press;
        # a press that only continues the prefix's held jump is no new press
        cmd = np.asarray(cmd)
        lat_h, _ = hold_filter_jit(np.concatenate([np.broadcast_to(np.asarray(prefix, np.int64), (len(cmd), P)), cmd],
                                                  axis=1), hold)
        rh = kin.rollout(start, lat_h, self.params, self.terrain, threads=1)
        cont0 = P > 0 and bool(int(prefix[-1]) & B_JUMP)
        ok_q = np.array([bool(rh.flags[q, P + c] & F_GROUND) or (c == 0 and cont0) for q, c in enumerate(cq)], bool)
        self.audit.hop_inflight += int((~ok_q).sum())
        if not ok_q.any():
            return None
        self.hop_dbg = {"on_p": on_p, "off_p": off_p, "clear": (a, z), "press": cs_, "bx": float(b[1])}
        return cmd[ok_q], [n for n, k in zip(names, ok_q) if k], np.asarray(bits, np.int64)[ok_q]

    def _sg8_slam_keys(self, start, r1, cmd, P: int, N: int, forced: bool, safe, n_map: int, M0: int):
        """SG8: (fs_bad, fs_face, offl) [N] for the selection's order (tick: the comment there); zeros outside a slam
        the map tracks this tick (MapHelper.info with the slam's frame)."""
        z = np.zeros(N)
        mi = self._map.info
        if mi is None or "k" not in mi or mi.get("cx") is None:
            return z, z, z
        from ssbot.combat import forum_map
        F = min(15, cmd.shape[1])
        md = r1.mode[:, P + 1:]
        fs_bad, fs_face, offl = z, z, z
        cx = float(mi["cx"])
        face = int(mi.get("face", 1))
        if forced:
            hx0 = 0.5 * (r1.box[:, P, 0] + r1.box[:, P, 2])
            xe = 0.5 * (r1.box[:, -1, 0] + r1.box[:, -1, 2])
            away = np.abs(xe - cx) > np.abs(hx0 - cx) + 1.0
            glide = (md == kin.M_GLIDE).any(axis=1)
            ds_ = np.isin(md, (kin.M_DASH, kin.M_SPRINT)).any(axis=1)
            fs_bad = (glide | (ds_ & away)).astype(np.float64)
            # the face band around where the Clapper stands at the row's end (its lunge: the variants' mean)
            from ssbot.combat import map_lookahead as ml
            st_ = ml.STAY
            if st_ is not None:
                ke = int(mi["k"]) + r1.box.shape[1] - 1
                x0 = float(mi["x0"])
                xm = (xe - x0) * face
                fs_face = np.array([ml.face_dist(float(v), ke, st_) for v in xm])
            self.audit.sg8_forced_slam += 1
        if n_map and bool(safe[M0]):
            att = ((cmd[:, :F] & B_ATTACK) != 0) & ((cmd[:, :F] & kin.B_DOWN) == 0)
            mo = np.isin(md[:, :F], (kin.M_DASH, kin.M_SPRINT, kin.M_GLIDE)).any(axis=1)
            offl = (mo | att.any(axis=1)).astype(np.float64)
            offl[M0] = 0.0
            self.audit.sg8_offl_rows += int(offl.sum())
        return fs_bad, fs_face, offl

    RUNE_C2_F = (48, 55)          # SG8: Cast 2 enters 48-55 frames after the Spell Antic entry (forum.md 33)

    def _sg8_rune_keys(self, f, start, r1, P: int, N: int, safe, hop_m) -> np.ndarray:
        """SG8 (the person's small-rune rules: no running away; on the ground at the 3-4 u face, one short hop over
        ring 1, no second jump press): [N] a tier for the safe rows while the nearest Clapper casts (Spell Antic,
        Cast 1, Cast 2): Cast 2: the hop rows -1, rows with a dash / sprint (the air dash away: 28 of 40 live casts)
        +2; before it: rows in the air at a frame Cast 2 can enter +1 (live: mid-hop at ~5 u when Cast 2 began)."""
        z = np.zeros(N)
        st0 = np.asarray(start).reshape(kin.K, -1)
        c = self._map._clapper(f, float(st0[kin.PX, 0]))
        if c is None:
            return z
        _, iid, tk, e, inst = c
        stt = next((m.get("state") for m in e.get("fsms") or () if m.get("name") == "Control"), None)
        if stt not in ("Spell Antic", "Cast 1", "Cast 2"):
            return z
        md = r1.mode[:, P + 1:]
        tier = np.where(np.isin(md, (kin.M_DASH, kin.M_SPRINT)).any(axis=1), 2.0, 0.0)
        if stt == "Cast 2":
            tier = np.where(hop_m, -1.0, tier)
        else:
            trk = getattr(getattr(f, "rs", None), "trk", None)
            T_, t0_ = getattr(trk, "T", None), getattr(inst, "t0", None)
            if T_ is not None and t0_ is not None:
                k = (float(T_) - float(t0_)) * 60.0
                a = int(max(P + 1, np.floor(self.RUNE_C2_F[0] - k)))
                b = int(min(r1.flags.shape[1] - 1, np.ceil(self.RUNE_C2_F[1] - k)))
                if a <= b:
                    air = ((r1.flags[:, a:b + 1] & F_GROUND) == 0).any(axis=1)
                    tier = tier + np.where(air, 1.0, 0.0)
        tier = np.where(safe, tier, 0.0)
        self.audit.sg8_hop_tier += int(stt == "Cast 2" and bool((safe & hop_m).any()))
        return tier

    def _chase_note_jc(self, f) -> None:
        """SSBOT_FORUM_CHASE (review): every tick, the tracker's time of each Clapper in a jump cast (CHASE_RUNE_S
        counts from its last tick wherever the hero is: beyond the map's NEAR_U, in a dash / recoil, on a wall)."""
        trk = getattr(getattr(f, "rs", None), "trk", None)
        if trk is None:
            return
        t_ = float(getattr(trk, "T", 0.0) or 0.0)
        for iid, (tk, e, inst) in (getattr(trk, "now", None) or {}).items():
            if getattr(inst, "fam", None) == "CC_JUMP_CAST" and (e.get("type_key") or tk) == "Song Heavy Sentry":
                self._chase_jc[int(iid)] = t_

    def _chase_rows(self, f, start, T: int):
        """SSBOT_FORUM_CHASE (task 1v1 SG5): toward the nearest Clapper (forum_map.MapHelper._clapper) while it idles,
        walks, evades or enters (CHASE_FAMS; not CHASE_RUNE_S after a jump cast): run (the side key) until the first
        press at k1 (CHASE_RUN_K, within CHASE_K_TOL of where the run reaches CHASE_AIM_U), or from farther than
        CHASE_DASH_U dash then run (CHASE_DASH_K), then a slash every CHASE_PERIOD frames with the side key held
        CHASE_FOLLOW frames from each press. Every check the other rows get. Review: none unless the map handles a
        slam it starts now (MapHelper.chase_gate: the map loaded, no wall exit; while it evades, where the scuttle
        ends). (cmd [n, T], names, prim bits) or None."""
        self.chase_off = None
        if self._map is None:
            return None
        st = np.asarray(start).reshape(kin.K, -1)
        hx = float(st[kin.PX, 0])
        c = self._map._clapper(f, hx)
        if c is None:
            return None
        d, iid, _, e, inst = c
        trk = getattr(getattr(f, "rs", None), "trk", None)
        t_ = float(getattr(trk, "T", 0.0) or 0.0)
        fam = getattr(inst, "fam", None) if inst is not None else None
        if fam not in CHASE_FAMS or d > CHASE_NEAR_U or t_ - self._chase_jc.get(iid, -1e9) <= CHASE_RUNE_S:
            return None
        cx = float(e["pos"][0])
        if abs(cx - hx) < 0.5:
            return None
        stt = next((m.get("state") for m in e.get("fsms") or () if m.get("name") == "Control"), None)
        gate = self._map.chase_gate(self._map.clapper_x(e, stt)[0], hx)
        if gate is not None:
            self.chase_off = gate
            return None
        dirb = kin.B_RIGHT if cx > hx else kin.B_LEFT
        # the first press where a run reaches the band (CHASE_K_TOL frames either side); the dash rows from afar only
        k_need = max(0.0, (abs(cx - hx) - CHASE_AIM_U) / CHASE_RUN_UF)
        run_k = [k for k in CHASE_RUN_K if abs(k - k_need) <= CHASE_K_TOL] or [max(CHASE_RUN_K)]
        dash_k = CHASE_DASH_K if abs(cx - hx) > CHASE_DASH_U else ()
        P = cmod.Prim
        b_run = cmod._bits(frozenset({P.MOVE, P.ATTACK_SIDE}))
        b_dash = cmod._bits(frozenset({P.MOVE, P.ATTACK_SIDE, P.DASH}))
        cmd, names, bits = [], [], []

        def presses(m, k1, fol):
            for k in range(k1, T, CHASE_PERIOD):
                m[k:k + cmod.PRESS] |= B_ATTACK
                m[k:k + fol] |= dirb
        for k1 in run_k:
            for fol in CHASE_FOLLOW:
                m = np.zeros(T, np.int64)
                m[:k1] = dirb
                presses(m, k1, fol)
                cmd.append(m)
                names.append(f"CHASE run{k1}_f{fol}")
                bits.append(b_run)
        for k1 in dash_k:
            for fol in CHASE_FOLLOW:
                m = np.zeros(T, np.int64)
                m[:k1] = dirb
                m[:cmod.PRESS] |= B_DASH
                presses(m, k1, fol)
                cmd.append(m)
                names.append(f"CHASE dash{k1}_f{fol}")
                bits.append(b_dash)
        return np.asarray(cmd), names, np.asarray(bits, np.int64)

    DS_REACH_U = 10.0             # the family runs only with a real target this close in x (box edge to hero centre)

    def _ds_hits(self, r, lat, face0: int, tbox, tok, treal, k_from, grow: float, shifts, stop: bool = False):
        """_ds_contact_kernel on rollout r (lanes over lat): (swing start, contact frame, target, robust) per row;
        stop: the robustness also with each target stopped where it is now."""
        n, T1 = r.flags.shape
        vr, vl, st, win = self.shapes
        o = (np.zeros(n, np.int64), np.zeros(n, np.int64), np.zeros(n, np.int64), np.zeros(n, np.bool_))
        _ds_contact_kernel(np.ascontiguousarray(r.box), np.ascontiguousarray(r.flags), np.ascontiguousarray(r.mode),
                           np.ascontiguousarray(lat), face0, np.ascontiguousarray(tbox[:, :T1]),
                           np.ascontiguousarray(tok[:, :T1]), treal, vr, vl, int(st[3]), int(st[4]),
                           int(win[3, 0]), int(win[3, 1]), np.ascontiguousarray(k_from, np.int64), float(grow),
                           shifts, np.ascontiguousarray(tbox[:, 0]) if stop else np.zeros((0, 4)), *o)
        return o

    @staticmethod
    def _ds_move_paths(trk, keep: list, tbox: np.ndarray) -> dict:
        """The certain-hit rule's body paths: per target in a tracked move (attack_range.Segmenter instance), its
        body now carried by the move template's displacement still to come (RangeTable.position, frame by frame), one
        path [T1, 4] per branch the move may take (the instance's branch once known, else every branch of the
        family): {target index: [paths]}. A target in a move without a template has none (never certain)."""
        from ssbot.combat.attack_range import bin_of
        out = {}
        now = getattr(trk, "now", None) or {}
        tabs = getattr(trk, "tables", None) or {}
        n = tbox.shape[1]
        for ti, t in enumerate(keep):
            if t.hazard or t.iid not in now:
                continue
            tk_, _e, inst = now[t.iid]
            tab = tabs.get(tk_)
            if inst is None or tab is None:
                continue
            b = bin_of(float(trk.T) - inst.t0)
            brs = (inst.branch,) if inst.branch else tuple(tab.spec.branches.get(inst.fam, ("main",)))
            paths = []
            for br in brs:
                tp = tab.templates.get((inst.fam, br))
                if tp is None:
                    continue
                p0 = tab.position(tp, b, (inst.x0, inst.y0), inst.s, inst.hero_du, inst.fam)
                d = np.array([tab.position(tp, b + k, (inst.x0, inst.y0), inst.s, inst.hero_du, inst.fam)
                              for k in range(n)], np.float64) - np.asarray(p0, np.float64)[None]
                paths.append(tbox[ti, 0][None, :] + np.stack([d[:, 0], d[:, 1], d[:, 0], d[:, 1]], axis=1))
            if paths:
                out[ti] = paths
        return out

    def _ds_cert(self, r, lat, face0: int, tbox, tok, treal, k_from, paths: dict, tgt: np.ndarray, cand: np.ndarray):
        """The certain-hit rule on rows `cand` (bool [n]) with first-strike target index tgt [n]: the strike meets the
        target on every one of its move paths (each branch), robust to CERT_SHIFTS frames on each, all at the same
        frame. Returns (certain [n], the contact frame on the move paths [n])."""
        n = len(tgt)
        ok = cand & np.array([int(t) in paths for t in tgt], bool)
        if not ok.any():
            return ok, np.full(n, -1, np.int64)
        nv = max(len(v) for v in paths.values())
        jv = []
        for v in range(nv):
            tb = tbox.copy()
            for ti, ps in paths.items():
                tb[ti] = ps[min(v, len(ps) - 1)]
            _, jj, tt, rr = self._ds_hits(r, lat, face0, tb, tok, treal, k_from, 0.0, dslash.CERT_SHIFTS)
            ok &= (jj >= 0) & (tt == tgt) & rr
            jv.append(jj)
        jv = np.stack(jv)
        ok &= (jv == jv[0][None]).all(axis=0)
        return ok, np.where(ok, jv[0], -1)

    def _ds_rows(self, ws, f, start, hold, prefix, prefs, T: int, posture: str):
        """SSBOT_FORUM_DSLASH (task 1v1 G3, combat.dslash): the delayed / chained down-slash rows of this tick, or None.
        Templates (ground: jump now x hold x press x key; air: press now or after w frames x key) rolled out to their
        press; kept when the blade meets a real target's predicted body (grown); the survivors with the key after the
        press, their contact and the certain-hit rule; the certain ones' bounce lanes; the chain (a second press
        CHAIN_B frames after the bounce, no jump press) where the second strike is certain too, its tail past the
        horizon checked against the support."""
        if not self.down_slash:
            return None                           # the crest's down attack is not a slash (the Reaper's dive)
        t0 = time.perf_counter()
        st = np.asarray(start).reshape(kin.K, -1)
        hx = float(st[kin.PX, 0])
        P = len(prefix)
        L = dslash.LMAX
        ft = self.params.frame_time
        tk_e = np.arange(P + L + 1, dtype=np.float64) * ft
        tbox, tok, _tw, keep = self._forum_targets(ws, f, tk_e, prefs)
        if not len(keep):
            return None
        treal = np.array([not t.hazard and not getattr(t, "blocked", False) for t in keep], np.bool_)
        near = treal & ((np.abs(tbox[:, 0, 0] - hx) < self.DS_REACH_U) | (np.abs(tbox[:, 0, 2] - hx) < self.DS_REACH_U))
        if not near.any():
            return None
        treal = treal & near
        a_ = self.audit
        a_.ds_ticks += 1
        jr = max(int(self.jump_until - self.ticks), 0) if posture == "air" else 0
        if not hasattr(self, "_ds_tpl"):
            self._ds_tpl = {}
        key = (posture, jr)
        if key not in self._ds_tpl:
            self._ds_tpl[key] = dslash.templates(posture, jr)
        M, PJ, NM = self._ds_tpl[key]
        if not len(M):
            return None
        face0 = 1 if st[kin.FACE, 0] >= 0 else -1
        prev = getattr(self, "_ds_prev", None)
        if special_mode.KEEP and getattr(self, "_kp", None) == "ds" and prev is not None and len(prev) > 1:
            # SSBOT_FORUM_SPECIAL_KEEP (G4 4b): a kept family row: no template search, only its continuation ("DS
            # cont" below: its contact and the checks verify it)
            X, XN, surv = np.zeros((0, T), np.int64), [], np.zeros(0, np.int64)
            a_.kp_skip += 1
        else:
            pre = np.broadcast_to(np.asarray(prefix, np.int64), (len(M), P))
            lat0, _ = hold_filter_jit(np.concatenate([pre, M], axis=1), hold)
            r0 = kin.rollout(start, lat0, self.params, self.terrain, threads=self.cfg.threads)
            _, j0, _, _ = self._ds_hits(r0, lat0, face0, tbox, tok, treal, np.full(len(M), P + 1, np.int64),
                                        dslash.PREFILTER_GROW_U, np.zeros(0, np.int64))
            surv = np.flatnonzero(j0 >= 0)
            if len(surv) > dslash.SURV_MAX:
                surv = surv[np.argsort(j0[surv], kind="stable")[:dslash.SURV_MAX]]
            a_.ds_tpl += len(M)
            a_.ds_pass += len(surv)
            X, _XP, XN = dslash.expand(M[surv], PJ[surv], [NM[i] for i in surv], T)
        if prev is not None and len(prev) > 1:
            # the previous tick's chosen family row, continued (its timing is off the grid one frame later)
            m = np.zeros(T, np.int64)
            k = min(T, len(prev) - 1)
            m[:k] = prev[1:1 + k]
            m[k:] = prev[-1] & (kin.B_LEFT | kin.B_RIGHT)
            X = np.concatenate([X, m[None]])
            XN = XN + ["DS cont"]
        if not len(X):
            self.ds_ms = (time.perf_counter() - t0) * 1e3
            return None
        n = len(X)
        lat1, _ = hold_filter_jit(np.concatenate([np.broadcast_to(np.asarray(prefix, np.int64), (n, P)), X], axis=1),
                                  hold)
        r1x = kin.rollout(start, lat1, self.params, self.terrain, threads=self.cfg.threads)
        _, c1, t1, rob1 = self._ds_hits(r1x, lat1, face0, tbox, tok, treal, np.full(n, P + 1, np.int64), 0.0,
                                        dslash.CERT_SHIFTS)
        hit = c1 >= 0
        if not hit.any():
            self.ds_ms = (time.perf_counter() - t0) * 1e3
            return None
        X, XN, lat1, c1, t1, rob1 = X[hit], [XN[i] for i in np.flatnonzero(hit)], lat1[hit], c1[hit], t1[hit], rob1[hit]
        r1x = kin.Rollout(r1x.phys[hit], r1x.pos[hit], r1x.vel[hit], r1x.mode[hit], r1x.flags[hit], r1x.final[:, hit],
                          r1x.box[hit])
        n = len(X)
        trk = getattr(getattr(f, "rs", None), "trk", None)
        now = getattr(trk, "now", {}) or {}
        inm = np.array([t.iid in now and now[t.iid][2] is not None for t in keep], bool)
        # review2: a swing under way at the start or pressed in the prefix (a strike already committed, e.g. the
        # chain's first press on its way) is outside the rows: its outcome (a bounce or not) is on no family lane, so
        # no row is certain this tick (every row on both branches: the miss lane and the scorer's hit branch, whose
        # first hit is that swing's; the certain lane and its hit branch's events would drop that bounce)
        busy = bool((r1x.flags[0, :P + 1] & F_ATTACKING).any() or (np.asarray(prefix, np.int64) & B_ATTACK).any())
        self.audit.ds_busy += int(busy)
        paths = self._ds_move_paths(trk, keep, tbox) if (dslash.CERT and inm.any() and not busy) else {}
        cert = np.zeros(n, bool)
        if paths:
            # the certain-hit rule on the move's own body path (the scorer's body moves on at its present velocity:
            # on the Clapper's slam that put strikes up to 9 u in front of where the body is)
            cert, cj = self._ds_cert(r1x, lat1, face0, tbox, tok, treal, np.full(n, P + 1, np.int64), paths, t1,
                                     inm[t1])
            cert &= cj < P + T
            c1 = np.where(cert, cj, c1)
        ev = np.zeros((n, P + T), np.int64)
        ci = np.flatnonzero(cert)
        ev[ci, c1[ci] - int(dslash.EVPRE)] = kin.EV_POGO       # EVPRE (G4): the bounce on the contact frame
        rows = [dict(cmd=X[q], ext=X[q], name=XN[q], ev=ev[q], cert=bool(cert[q]), c1=int(c1[q]), c2=-1,
                     tgt=int(keep[int(t1[q])].iid), extra=0, lane=None) for q in range(n)]
        if len(ci):
            rb = kin.rollout(start, lat1[ci], self.params, self.terrain, events=ev[ci], threads=self.cfg.threads)
            for m_, q in enumerate(ci):
                rows[q]["lane"] = (rb, m_)
        n_chain = 0
        # review2: a certain row that already holds a second press (the continued chain, "DS cont", once its second
        # press is inside the horizon) has no bounce event for it: its lane is the second strike's miss and the
        # certified second bounce is on no lane. It is judged only as its chain twin (the same masks, the second
        # press re-certified, both bounces on the lane); without a certain twin it is not offered.
        two = np.zeros(n, np.int64)
        for q in ci:
            a_on = (X[q] & B_ATTACK) != 0
            rz = np.flatnonzero(a_on & ~np.concatenate([[False], a_on[:-1]]))
            two[q] = int(rz[1]) if len(rz) > 1 else -1
        two[np.setdiff1d(np.arange(n), ci)] = -1
        drop_q = set(int(q) for q in ci if two[q] >= 0)
        self.audit.ds_cont2 += len(drop_q)
        if dslash.CHAIN and len(ci):
            # the second strike: pressed CHAIN_B frames after the first bounce, no jump press in the air
            cr, cb, cq = [], [], []
            for q in ci:
                for b in ((int(two[q]) - (int(c1[q]) - P),) if two[q] >= 0 else dslash.CHAIN_B):
                    p2 = int(c1[q]) - P + b
                    if b > 0 and p2 + 1 + int(self.shapes[3][3, 1]) <= L:
                        cr.append(q)
                        cb.append(p2)
            if cr:
                Lc = max(T, min(L, max(cb) + dslash.POST_F))
                C = np.stack([dslash.chain(X[q], p2, Lc) for q, p2 in zip(cr, cb)])
                cr = np.asarray(cr, np.int64)
                nc = len(C)
                latc, _ = hold_filter_jit(np.concatenate([np.broadcast_to(np.asarray(prefix, np.int64), (nc, P)), C],
                                                         axis=1), hold)
                evc = np.zeros((nc, P + Lc), np.int64)
                evc[np.arange(nc), c1[cr] - int(dslash.EVPRE)] = kin.EV_POGO
                rcb = kin.rollout(start, latc, self.params, self.terrain, events=evc, threads=self.cfg.threads)
                _, c2, t2, _ = self._ds_hits(rcb, latc, face0, tbox, tok, treal, c1[cr] + 1, 0.0,
                                             np.zeros(0, np.int64))
                ok2, c2m = self._ds_cert(rcb, latc, face0, tbox, tok, treal, c1[cr] + 1, paths, np.maximum(t2, 0),
                                         (c2 >= 0) & inm[np.maximum(t2, 0)])
                c2 = np.where(ok2, c2m, c2)
                ok2 &= c2 < P + Lc
                # per first strike at most two second presses (the earliest and the latest that connect)
                pick = []
                kb = getattr(self, "_ds_keep_b", None) if special_mode.KEEP else None
                for q in np.unique(cr[ok2]):
                    w_ = np.flatnonzero(ok2 & (cr == q))
                    if kb is not None and XN[q] == "DS cont":
                        # G4 4b: the kept chain's own second press (its offset after the bounce) comes first
                        pick = [int(w) for w in w_ if cb[w] - (int(c1[q]) - P) == kb] + pick
                    pick += [w for w in sorted({int(w_[0]), int(w_[-1])}) if w not in pick]
                pick = np.asarray(pick[:dslash.CHAIN_MAX], np.int64)
                if len(pick):
                    evc2 = evc[pick].copy()
                    evc2[np.arange(len(pick)), c2[pick] - int(dslash.EVPRE)] |= kin.EV_POGO
                    lt = latc[pick]
                    rp = kin.rollout(start, lt[:, :P + T], self.params, self.terrain, events=evc2[:, :P + T],
                                     threads=self.cfg.threads)
                    rt = kin.rollout(rp.final, lt[:, P + T:], self.params, self.terrain, events=evc2[:, P + T:],
                                     threads=self.cfg.threads)
                    # the tail past the horizon (the second strike and its bounce) against the support
                    T1 = P + T + 1
                    bx = rt.box[:, 1:]
                    tq = (T1 + np.arange(bx.shape[1])) * ft
                    o = f.occupied(0.5 * (bx[..., 0] + bx[..., 2]), 0.5 * (bx[..., 1] + bx[..., 3]), tq)
                    o &= (rt.flags[:, 1:] & F_INVULN) == 0
                    tail_ok = ~o.any(axis=1)
                    a_.ds_chain_tail_fail += int((~tail_ok).sum())
                    for m_, w_ in enumerate(pick):
                        if not tail_ok[m_]:
                            continue
                        q = int(cr[w_])
                        evq = np.zeros(P + T, np.int64)
                        evq[:] = evc2[m_, :P + T]
                        rows.append(dict(cmd=C[w_, :T], ext=C[w_], name=f"{XN[q]}+c{cb[w_] - (int(c1[q]) - P)}",
                                         ev=evq, cert=True, c1=int(c1[q]), c2=int(c2[w_]),
                                         tgt=int(keep[int(t1[q])].iid), extra=int(c2[w_] >= T1), lane=(rp, m_)))
                        n_chain += 1
        if drop_q:
            rows = [r_ for i, r_ in enumerate(rows) if i not in drop_q]
            if not rows:
                self.ds_ms = (time.perf_counter() - t0) * 1e3
                return None
        # at most MAX_ROWS: the chains, then the certain rows, then the others; the earliest contact first
        order = sorted(range(len(rows)), key=lambda i: (rows[i]["c2"] < 0, not rows[i]["cert"], rows[i]["c1"]))
        rows = [rows[i] for i in order[:dslash.MAX_ROWS]]
        n = len(rows)
        cert = np.array([r_["cert"] for r_ in rows], bool)
        lane = None
        if cert.any():
            lane = {}
            for nm in ("phys", "pos", "vel", "mode", "flags", "box"):
                lane[nm] = np.stack([getattr(r_["lane"][0], nm)[r_["lane"][1]] for r_ in rows if r_["cert"]])
            lane["final"] = np.stack([r_["lane"][0].final[:, r_["lane"][1]] for r_ in rows if r_["cert"]], axis=1)
        a_.ds_rows += n
        a_.ds_cert += int(cert.sum())
        a_.ds_chain += sum(1 for r_ in rows if r_["c2"] >= 0)
        ms = (time.perf_counter() - t0) * 1e3
        a_.ds_ms += ms
        return DsRows(np.stack([r_["cmd"] for r_ in rows]), [r_["name"] for r_ in rows], [r_["ext"] for r_ in rows],
                      np.stack([r_["ev"] for r_ in rows]), cert, np.array([r_["c1"] for r_ in rows], np.int64),
                      np.array([r_["c2"] for r_ in rows], np.int64), np.array([r_["tgt"] for r_ in rows], np.int64),
                      np.array([r_["extra"] for r_ in rows], np.int64), lane, len(M), len(surv), n_chain, ms)

    def warm_win(self, S) -> None:
        """Task oldwin: _win_rows' rollout paths with their array layouts (the bounce lanes: fancy-indexed rows with
        events; the miss lanes and the long tails from contiguous arrays) and the planner's strike model on them
        (stage F: always on) - the first window tick of a replay compiled them mid-fight (1.8 s)."""
        T, P, th = int(self.fcfg.T), 2, self.cfg.threads
        lat = np.zeros((3, P + T + 24), np.int64)
        ev = np.zeros((3, P + T), np.int64)
        ev[:, 12] = kin.EV_POGO
        ci = np.array([0, 2], np.int64)
        kin.rollout(S, lat[ci, :P + T], self.params, self.terrain, events=ev[ci], threads=th)
        lw_ = np.zeros((3, P + T + 24), np.int64)
        rm = kin.rollout(S, lw_, self.params, self.terrain, threads=th)
        evl = np.zeros((2, P + T + 24), np.int64)
        evl[:, P + T + 5] = kin.EV_POGO
        kin.rollout(S, np.ascontiguousarray(lw_[ci]), self.params, self.terrain, events=evl, threads=th)
        tb = np.full((1, P + T + 25, 4), np.nan)
        self._ds_hits(rm, lw_, 1, tb, np.zeros((1, P + T + 25), np.bool_), np.ones(1, np.bool_),
                      np.full(3, P + 1, np.int64), 0.0, np.zeros(0, np.int64))

    def _win_rows(self, win_, ws, f, start, hold, prefix, prefs, T: int, posture: str, ds):
        """Task oldwin (SSBOT_FORUM_WINDOWS=1; the policy sets self.win = ssbot.map2.oldwin.WindowRows, None: nothing
        here runs): the strike-window table's rows (now / approach / the chosen one's continuation; win_.rows finds
        them) as certain-hit family rows (combat.dslash G3) appended to this tick's family rows `ds` (None: they are
        the family): the macro latched unchanged by the hold filter after the keys in flight, the contact from the
        table (k_strike's earliest outcome) on its target, the bounce lane from the contact; a contact past the
        horizon (<= LONG_MAX frames): the row within the horizon as any row, its tail to the contact + POST_F against
        the support with the bounce, the strike credited ('extra'). Every other check is the planner's own. Stage F:
        certain (the bounce lane / the credit) only where the planner's own strike model agrees with the table's
        contact (frame and target), else judged on its own lane; the bounce on the mask before the contact."""
        t0 = time.perf_counter()
        a_ = self.audit
        P = len(prefix)
        fo = int(ws.stamp.frame)
        fr = fo + P - 1                       # the policy's frame (the prefix holds fo + 1 .. fr + 1)
        cands, info = win_.rows(start, prefix, hold, T, self.params, self.terrain, hold_filter_jit, fr, fo,
                                self.cfg.threads, posture)
        self._win_info = {"ms": round(info["ms"], 3)}
        for k_ in ("cl", "part", "cd", "off", "edge"):
            if info[k_]:
                self._win_info[k_] = dict(info[k_])
        for k_ in ("appr_found", "appr_rekey_miss", "cont", "cont_end", "cont_keys", "cont_dev", "cont_clapper",
                   "cont_freeze", "cont_rekey", "cont_vel"):
            if info[k_]:
                self._win_info[k_] = int(info[k_])
        if info["gate"]:
            self._win_info["gate"] = info["gate"]
        if not cands:
            self._win_info["ms_all"] = round((time.perf_counter() - t0) * 1e3, 3)
            return ds
        LONG_MAX, POST_F = 24, dslash.POST_F
        L = max(T, max(len(c.cmd) for c in cands))
        n = len(cands)
        X = np.zeros((n, L), np.int64)
        for q, c in enumerate(cands):
            X[q, :len(c.cmd)] = c.cmd
        pre = np.broadcast_to(np.asarray(prefix, np.int64), (n, P))
        lat, _ = hold_filter_jit(np.concatenate([pre, X], axis=1), hold)
        keep_q, why = [], Counter()
        for q, c in enumerate(cands):
            if not np.array_equal(lat[q, P:P + len(c.cmd)], X[q, :len(c.cmd)]):
                why["hold"] += 1                       # the filter changes the macro: not the table's keys
            elif c.k0 <= P:                            # (the bounce's mask c.k0 - 1 is in the prefix)
                why["past"] += 1
            elif c.k0 > P + T + LONG_MAX:
                why["far"] += 1
            else:
                keep_q.append(q)
        if why:
            self._win_info["drop"] = dict(why)
        if not keep_q:
            self._win_info["ms_all"] = round((time.perf_counter() - t0) * 1e3, 3)
            return ds
        cands = [cands[q] for q in keep_q]
        X, lat = X[keep_q], lat[keep_q]
        n = len(cands)
        c1 = np.array([int(c.k0) for c in cands], np.int64)
        inh = c1 < P + T
        th = self.cfg.threads
        ft = self.params.frame_time
        st_ = np.asarray(start).reshape(kin.K, -1)
        face0 = 1 if st_[kin.FACE, 0] >= 0 else -1
        # stage F (review findings 1 / 7): the planner's own strike model on the row's own lane (no bounce: the lane if
        # the slash missed). A row is a certain hit (judged on its bounce lane) only when the planner's first strike
        # contact is on the row's target AT the table's contact frame - two independent models agree; otherwise it is
        # judged on its own (miss) lane as any row (the scorer credits a hit only where its model sees one) and a long
        # row gets no strike credit, its tail judged without the bounce. SSBOT_FORUM_WINDOWS_PLC=0: every row certain
        li = np.flatnonzero(~inh)
        Lt = T
        if len(li):
            Lt = max(T + 1, int(max(int(c1[q]) - P + POST_F for q in li)))
        Lw = P + max(Lt, T)
        lw_ = np.zeros((n, Lw), np.int64)               # the rows' latched keys to the long tails' end (no keys after)
        w_ = min(Lw, lat.shape[1])
        lw_[:, :w_] = lat[:, :w_]
        rm = kin.rollout(start, lw_, self.params, self.terrain, threads=th)     # the miss lanes
        c_pl = np.full(n, -1, np.int64)
        tk_e = np.arange(Lw + 1, dtype=np.float64) * ft
        tbox, tok, _tw, keep = self._forum_targets(ws, f, tk_e, prefs)
        if len(keep):
            treal = np.array([not t.hazard and not getattr(t, "blocked", False) for t in keep], np.bool_)
            _, cc, tt, _ = self._ds_hits(rm, lw_, face0, tbox, tok, treal, np.full(n, P + 1, np.int64), 0.0,
                                         np.zeros(0, np.int64))
            for q in range(n):
                c_pl[q] = int(cc[q]) if cc[q] >= 0 and int(keep[int(tt[q])].iid) == cands[q].iid \
                    else (-1 if cc[q] < 0 else -3)
        agree = (c_pl == c1) | (not WIN_PLC)
        cert = inh & agree
        ev = np.zeros((n, P + T), np.int64)
        # stage F (finding 5): the bounce on the mask BEFORE the contact frame (the table's / map2's ev[c - 1]; the
        # rollout's state c follows mask c - 1), whatever SSBOT_FORUM_DSLASH_EVPRE says for the family's rows
        ev[np.flatnonzero(cert), c1[cert] - 1] = kin.EV_POGO
        extra = np.zeros(n, np.int64)
        ok = np.ones(n, bool)
        lane = None
        if cert.any():
            ci = np.flatnonzero(cert)
            rb = kin.rollout(start, lat[ci, :P + T], self.params, self.terrain, events=ev[ci], threads=th)
            lane = {nm: getattr(rb, nm) for nm in ("phys", "pos", "vel", "mode", "flags", "box")}
            lane["final"] = rb.final
        if len(li):
            # the long rows' tail past the horizon (to the contact + POST_F; past the row's keys none) against the
            # support - stage F (finding 11): every corner of her box and its centre, F_INVULN skipped; a row the two
            # models agree on with the bounce (its strike credited), any other one on its miss lane (no credit)
            ag = agree[li]
            evl = np.zeros((len(li), Lw), np.int64)
            for m_, q in enumerate(li):
                if ag[m_] and int(c1[q]) - 1 < Lw:
                    evl[m_, int(c1[q]) - 1] = kin.EV_POGO
            rt = kin.rollout(start, np.ascontiguousarray(lw_[li]), self.params, self.terrain, events=evl, threads=th)
            T1 = P + T + 1
            bx = rt.box[:, T1:]
            tq = (T1 + np.arange(bx.shape[1])) * ft
            o = np.zeros(bx.shape[:2], bool)
            for xs, ys in ((0.5 * (bx[..., 0] + bx[..., 2]), 0.5 * (bx[..., 1] + bx[..., 3])),
                           (bx[..., 0], bx[..., 1]), (bx[..., 2], bx[..., 1]), (bx[..., 0], bx[..., 3]),
                           (bx[..., 2], bx[..., 3])):
                o |= f.occupied(np.ascontiguousarray(xs), np.ascontiguousarray(ys), tq)
            o &= (rt.flags[:, T1:] & F_INVULN) == 0
            for m_, q in enumerate(li):
                lim = int(c1[q]) - P + POST_F - T
                if o[m_, :max(lim, 1)].any():
                    ok[q] = False
                elif ag[m_]:
                    extra[q] = 1
            self._win_info["tail_fail"] = int((~ok[li]).sum())
        sel = np.flatnonzero(ok)
        self._win_info["nocert"] = int((inh & ~agree).sum())
        if not len(sel):
            self._win_info["ms_all"] = round((time.perf_counter() - t0) * 1e3, 3)
            return ds
        for q in range(n):
            cands[q].cert = bool(cert[q] or extra[q])
        cands = [cands[q] for q in sel]
        names = [f"WIN {c.kind} {c.wt} {c.label}" + (f" {c.tpl}@{c.j}" if c.kind == "appr" else "") +
                 ("" if c.cert else " nc") for c in cands]
        ext = [X[q, :max(len(cands[m_].cmd), T)] for m_, q in enumerate(sel)]
        # the lane rows = the certain rows in order (every certain row is in sel: only long rows fail ok)
        wr = DsRows(X[sel, :T], names, ext, ev[sel], cert[sel].astype(bool), c1[sel], np.full(len(sel), -1, np.int64),
                    np.array([c.iid for c in cands], np.int64), extra[sel], lane, n, len(sel), 0, 0.0)
        self._win_info["gen"] = dict(Counter(c.wt for c in cands))
        self._win_info["kind"] = dict(Counter(c.kind for c in cands))
        self._win_info["rows"] = [[c.kind, c.wt, int(c.k0) - P, int(c_pl[q]) - P if c_pl[q] >= 0 else int(c_pl[q]),
                                   int(extra[q]), int(cert[q])] for c, q in zip(cands, sel)]
        a_.win_rows += len(sel)
        a_.win_ticks += 1
        if ds is None:
            self._win_off = 0
            self._win_c = cands
            self._win_info["ms_all"] = round((time.perf_counter() - t0) * 1e3, 3)
            return wr
        # appended to the family's own rows (SSBOT_FORUM_DSLASH on too)
        self._win_off = len(ds.cmd)
        self._win_c = cands
        if ds.lane is None or wr.lane is None:
            ln = ds.lane if wr.lane is None else wr.lane
        else:
            ln = {nm: (np.concatenate([ds.lane[nm], wr.lane[nm]]) if nm != "final" else
                       np.concatenate([ds.lane[nm], wr.lane[nm]], axis=1)) for nm in ds.lane}
        out = DsRows(np.concatenate([ds.cmd, wr.cmd]), list(ds.names) + names, list(ds.ext) + ext,
                     np.concatenate([ds.ev, wr.ev]), np.concatenate([ds.cert, wr.cert]), np.concatenate([ds.c1, wr.c1]),
                     np.concatenate([ds.c2, wr.c2]), np.concatenate([ds.tgt, wr.tgt]),
                     np.concatenate([ds.extra, wr.extra]), ln, ds.n_tpl, ds.n_pass, ds.n_chain, ds.ms)
        self._win_info["ms_all"] = round((time.perf_counter() - t0) * 1e3, 3)
        return out

    def _special_ctx(self, f, start, hold, prefix, latched, r1, rows: np.ndarray, exts: list, T: int):
        """The special mode's tick context (combat.special_mode): the special rows' contact with E's move (the bounce
        event), their bounce lanes spliced into r1 (stage 1 and the score read the bounce from the press on), the
        certified window, the special support (special_stacks: E's move dropped, its body and hazards kept, every
        other enemy kept) and each row's continuation past its end (exts: the row's whole template) checked against
        it (tail_ok). Rows without a contact in the model are left out (they keep the full checks). None: no row."""
        from ssbot.combat.forum_v2 import ESC_F
        t0 = time.perf_counter()
        meta = getattr(self, "_spec_meta", None)
        rs = getattr(f, "rs", None)
        tl = special_mode.timeline(meta["move"]) if meta else None
        if tl is None or rs is None or not len(rows):
            return None
        P = len(prefix)
        n = len(rows)
        T1 = P + T + 1
        L = max(max(len(x) for x in exts), T + ESC_F)
        ext = np.zeros((n, P + L), np.int64)
        ext[:, :P] = prefix
        for q, x in enumerate(exts):
            ext[q, P:P + len(x)] = x
            ext[q, P + len(x):] = x[-1] & (kin.B_LEFT | kin.B_RIGHT)
        lat_e, _ = hold_filter_jit(ext, hold)
        k0, xa, cy, face = meta["k0"], meta["xa"], meta["cy"], meta["face"]
        from ssbot.combat.pogo_model import ACTIVE
        pj = np.zeros(n, np.int64)
        hf = np.zeros(n, np.int64)
        for q in range(n):
            dn = np.flatnonzero(((ext[q, P:] & B_DOWN) != 0) & ((ext[q, P:] & B_ATTACK) != 0))
            if len(dn):
                pj[q] = P + int(dn[0]) + 1
                hf[q] = special_mode.facing_at(start, ext[q], P + int(dn[0]))
        # the miss lanes for the contact: r1's (the planner's lanes) when the slash's window ends within them, else
        # the whole template rolled out
        inside = (pj > 0) & (pj + ACTIVE[1] <= T1 - 1)
        if inside.all():
            mpos, mfl, mvel = r1.pos[rows], r1.flags[rows], r1.vel[rows]
        else:
            re = kin.rollout(start, lat_e, self.params, self.terrain, threads=self.cfg.threads)
            mpos, mfl, mvel = re.pos, re.flags, re.vel
        contact = special_mode.contacts(tl, mpos, mfl, pj, k0, xa, cy, face, hf)
        by_map = bool(meta.get("by_map"))
        if by_map:
            # SG4: the map certifies its rows on the Clapper's whole move (a row without a press or contact on the
            # lane too: no bounce event, E's move still dropped)
            keep = np.ones(n, bool)
        else:
            keep = contact > 0
            # review: the press must lie in a certified entry on this lane (hold-filtered; the CONTINUE is not looked
            # up by strike_rows): else the row keeps the full checks
            cert = special_mode.press_certified(meta.get("lut"), self._spec_disp, mpos, mvel, mfl, pj, ext, k0, xa,
                                                cy, face)
            self.audit.sm_uncert += int((keep & ~cert).sum())
            keep &= cert
        if not keep.any():
            return None
        ev = np.zeros((n, P + L), np.int64)
        hc = keep & (contact > 0)
        ev[np.flatnonzero(hc), contact[hc] - 1] = kin.EV_POGO     # SlamTheory's convention (the certified bounce)
        if by_map:
            # review: every bounce of the map's lane (a second strike's too: without it the lane fell where the map
            # bounced); the first must be the lane's own contact (special_mode.contacts), else the row keeps the
            # full checks
            mev = [int(e_) for e_ in meta.get("map_ev") or () if 0 <= int(e_) < P + L]
            first_ok = (contact == (mev[0] + 1 if mev else -1)) | ((contact <= 0) & (not mev))
            self.audit.map_lane_contact += int((~first_ok).sum())
            keep &= first_ok
            if not keep.any():
                return None
            ev[:] = 0
            for e_ in mev:
                ev[:, e_] = kin.EV_POGO
        rows, ext, lat_e, ev, contact, pj = rows[keep], ext[keep], lat_e[keep], ev[keep], contact[keep], pj[keep]
        is_long = pj - P - 1 > T - 2                # the press past the horizon (strike_rows' long rows)
        n = len(rows)

        def bounce(lat_, ev_):
            """The bounce lanes: the planner's length (r1's splice, the end state for the escape) and the rest of the
            template continued from there (the tail check, the certified window); arrays over the whole length."""
            rp_ = kin.rollout(start, lat_[:, :P + T], self.params, self.terrain, events=ev_[:, :P + T],
                              threads=self.cfg.threads)
            rt_ = kin.rollout(rp_.final, lat_[:, P + T:], self.params, self.terrain, events=ev_[:, P + T:],
                              threads=self.cfg.threads)
            return rp_, {nm: np.concatenate([getattr(rp_, nm), getattr(rt_, nm)[:, 1:]], axis=1)
                         for nm in ("box", "flags", "pos")}
        rp, rb = bounce(lat_e, ev)
        if by_map and meta.get("map_x") is not None:
            # review: the lane the planner judges must be the map's own (the map alone certifies the Clapper's move on
            # it): the hold-filtered keys rolled out with the map's bounces stay within one run step (x) and the
            # map's y dilation of the map's path, else the row keeps the full checks (a model mismatch: the hold
            # filter, terrain, a phase)
            mx_, my_ = np.asarray(meta["map_x"], float), np.asarray(meta["map_y"], float)
            m_ = int(min(len(mx_), rb["box"].shape[1] - P - 1))
            bxm = rb["box"][:, P + 1:P + 1 + m_]
            dx_ = np.abs(0.5 * (bxm[..., 0] + bxm[..., 2]) - mx_[None, :m_]).max(axis=1) if m_ else np.zeros(n)
            dy_ = np.abs(bxm[..., 1] - my_[None, :m_]).max(axis=1) if m_ else np.zeros(n)
            lane_ok = (dx_ <= MAP_LANE_TOL_X) & (dy_ <= MAP_LANE_TOL_Y)
            self.audit.map_lane_off += int((~lane_ok).sum())
            meta["lane_dx"], meta["lane_dy"] = round(float(dx_.max()), 3), round(float(dy_.max()), 3)
            if not lane_ok.all():
                if not lane_ok.any():
                    return None
                rows, ext, lat_e, ev, contact, pj, is_long = (a_[lane_ok] for a_ in (rows, ext, lat_e, ev, contact, pj,
                                                                                    is_long))
                rp, rb = bounce(lat_e, ev)
                n = len(rows)
        # T1's real-box approach check: 0 clear, 1 the root box (body), 2 the attack box; -1 not computed (without
        # SSBOT_FORUM_SPECIAL_APPR only the chosen row's, at the selection: a diagnostic)
        appr = special_mode.approach_codes(tl, k0, xa, cy, face, pj, rb["box"], rb["flags"]) \
            if special_mode.APPR else np.full(n, -1, np.int64)
        if special_mode.APPR and appr.any() and not by_map:
            # SSBOT_FORUM_SPECIAL_APPR: T1's real-box approach check as a filter (the rows failing it keep the
            # full checks)
            k2 = appr == 0
            if not k2.any():
                return None
            rows, ext, lat_e, ev, contact, pj, is_long, appr = (a_[k2] for a_ in (rows, ext, lat_e, ev, contact, pj,
                                                                                  is_long, appr))
            rp, rb = bounce(lat_e, ev)
            n = len(rows)
        Lb = rb["flags"].shape[1]
        cert_end = np.zeros(n, np.int64)
        for q in range(n):
            g = np.flatnonzero((rb["flags"][q, contact[q] + 1:] & F_GROUND) != 0)
            land = int(contact[q]) + 1 + int(g[0]) if len(g) else Lb - 1
            cert_end[q] = min(land, int(pj[q]) + special_mode.CERT_AFTER)
        al = special_mode.active_last(tl)
        big = 1 << 30
        full_from = np.where(k0 + cert_end <= al, cert_end, big).astype(np.int64)
        if by_map:
            cert_end[:] = Lb - 1
            # the map certifies E's move to its end; review: from the frame every observed variant has ended on (the
            # Clapper may start its next move) the full support is read again (big dropped E's next move from the
            # row's last frames and its tail)
            full_from[:] = max(0, int(meta.get("k_full", big)) - int(k0)) if meta.get("k_full") is not None else big
        # the planner lanes: the bounce from the press on (the score, stage 1, the end state for the escape)
        for nm in ("phys", "pos", "vel", "mode", "flags", "box"):
            getattr(r1, nm)[rows] = getattr(rp, nm)
        r1.final[:, rows] = rp.final
        st_o, es_o = rs.special_stacks(meta["iid"], list(getattr(rs, "haz_raw", {}).get(meta["iid"], ())))
        st_b, es_b = special_mode.body_stacks(rs, meta["iid"], tl, meta["k_trk"], xa, cy, face, meta["tk"])
        ctx = special_mode.SpecialCtx(meta["iid"], meta["move"], k0, xa, cy, face, tl, st_o, es_o, st_b, es_b, rows,
                                      contact, cert_end, full_from, ev[:, :P + T], np.ones(n, bool), pj, is_long)
        idx = np.arange(T1, Lb)
        if len(idx):
            bx = rb["box"][:, idx]
            tq = idx * self.params.frame_time
            o = special_mode.occ_special(ctx, rs, np.arange(n), 0.5 * (bx[..., 0] + bx[..., 2]),
                                         0.5 * (bx[..., 1] + bx[..., 3]), tq)
            o &= (rb["flags"][:, idx] & F_INVULN) == 0
            ctx.tail_ok = ~o.any(axis=1)
        ctx.box, ctx.flags, ctx.pos, ctx.appr_fail = rb["box"], rb["flags"], rb["pos"], appr
        ctx.ext = ext[:, P:]
        ctx.ms = (time.perf_counter() - t0) * 1e3
        return ctx

    def _v2_dash(self, o: np.ndarray, f, r1, cx: np.ndarray, cy: np.ndarray, tq: np.ndarray, fr) -> np.ndarray:
        """The focus margin (forum_v2 MARGIN_MODE "focus", the person 2026-10-11): a row that dashes at the focus
        unit reads that unit with its "rule" margin (occupied_dash) on stage 1's frames; every other row keeps
        FOCUS_M. The rows in contact only that way (v2_dash_only, also last_info["dash_only"]) get S = 1 at the selection, after the
        envelope, the hit branches and their caps ran as without the rule (forum.md 46.1: applied at stage 1 they
        shifted the caps and changed 7-20 % of the 1v1 picks though no pick of the flat-0.5 arm was such a row).
        The envelope, the hit branches and the escapes read the plain support."""
        self.v2_dash_only = np.zeros(0, np.int64)
        rs = getattr(f, "rs", None)
        if rs is None or getattr(rs, "stack_dash", None) is None or rs.dash_focus not in getattr(rs.trk, "now", {}):
            return o
        p = rs.trk.now[rs.dash_focus][1].get("pos")
        if not p or forum_v2.jb_dash_free(rs):
            return o
        dr = forum_v2.dash_at(r1.mode, r1.vel, r1.centre, float(p[0]))
        if not dr.any():
            return o
        od = rs.occupied_dash(cx[dr], cy[dr], tq)
        only = od.any(axis=1) & ~o[dr].any(axis=1)
        self.audit.v2_dash_rows += int(dr.sum())
        self.audit.v2_dash_unsafe += int(only.sum())
        self.v2_dash_only = np.flatnonzero(dr)[only]
        return o           # applied at the selection (tick: S of these rows = 1 after the branches and their caps)

    def tick(self, ws, start: np.ndarray, hold: HoldState, prefix: np.ndarray, f, prefs, ctx: FilterContext
             ) -> PlanResult:
        t0 = time.perf_counter()
        if self.measurement_enabled:
            self.measurement_result = None
        cfg, fcfg, params = self.cfg, self.fcfg, self.params
        v2 = bool(fcfg.v2 and getattr(f, "v2", False))
        prefix = np.asarray(prefix, np.int64).reshape(-1)
        P = len(prefix)
        posture = posture_of(start)
        mode0 = int(np.asarray(start).reshape(kin.K, -1)[kin.MODE, 0])
        cs, core0 = (self.fsets_nc if mode0 in NO_CONTROL_MODES else self.fsets)[posture]
        N0, T = len(cs.cmd), cs.T
        cont = self.prev_cmd is not None
        rows_ = [cs.cmd]
        self._spec_meta = None
        pv_sm = getattr(self, "_prev_sm", None)          # the special mode: last tick's chosen special row
        self._prev_sm = None
        self._pv_sm_now = pv_sm
        spec = self._special_rows(f, start, prefix, T) if (v2 and (specials.SPECIALS_ON or special_mode.SPECIAL_MODE))             else None
        n_spec = 0 if spec is None else len(spec.cmd)
        if n_spec:
            rows_.append(spec.cmd)               # the arrive-and-strike rows: after the set, before the CONTINUE
        hop = None
        if v2 and rune_bombs.HOP and posture == "ground" and mode0 not in NO_CONTROL_MODES:
            hop = self._rune_hop_rows(f, start, hold, prefix, T)
        n_chase = 0
        if CHASE:
            self._chase_note_jc(f)               # review: every tick (CHASE_RUNE_S from the jump cast's last tick)
        if CHASE and v2 and mode0 not in NO_CONTROL_MODES and posture in ("ground", "air"):
            # SG5: the chase rows after the hop rows, in the same block (not core: enveloped in the order like the
            # set's rows, so they cannot push the escape check past its deadline)
            ch_ = self._chase_rows(f, start, T)
            if ch_ is not None:
                n_chase = len(ch_[0])
                hop = ch_ if hop is None else (np.concatenate([hop[0], ch_[0]]), list(hop[1]) + list(ch_[1]),
                                               np.concatenate([np.asarray(hop[2], np.int64), ch_[2]]))
        n_hop = 0 if hop is None else len(hop[0])
        if n_hop:
            rows_.append(hop[0])                 # the person's hop rows (G2): after the special rows
        ds = None
        if v2 and dslash.DSLASH and mode0 not in NO_CONTROL_MODES and posture in ("ground", "air"):
            ds = self._ds_rows(ws, f, start, hold, prefix, prefs, T, posture)
        win_ = getattr(self, "win", None)        # task oldwin (SSBOT_FORUM_WINDOWS; None: off, nothing runs)
        if win_ is not None:
            self._win_c, self._win_info = None, None
            if v2 and self.down_slash and mode0 not in NO_CONTROL_MODES and posture in ("ground", "air"):
                ds = self._win_rows(win_, ws, f, start, hold, prefix, prefs, T, posture, ds)
        self._ds = ds
        n_ds = 0 if ds is None else len(ds.cmd)
        D0 = N0 + n_spec + n_hop
        self._ds_D0 = D0
        if n_ds:
            rows_.append(ds.cmd)                 # the delayed / chained down slashes (G3): after the hop rows
        mrow = None
        map_ms = 0.0                              # review: the map's own work this tick (MAP_DL_SHIFT)
        if SPECIAL_MAP:
            tm_ = time.perf_counter()
            from ssbot.combat import forum_map
            forum_map.BOARD.clear()
            if self._map is None:
                self._map = forum_map.MapHelper(self)
            if not self._map._loaded:
                self._map.preload()               # review: the first tick with the arena's terrain
            self._map.info = None
            if v2 and mode0 not in NO_CONTROL_MODES:
                mrow = self._map.row(f, start, hold, prefix, T, self.ticks)
            map_ms += (time.perf_counter() - tm_) * 1e3
        n_map = 0 if mrow is None else 1
        M0 = D0 + n_ds
        if n_map:
            rows_.append(mrow.cmd[None])          # SG4: the map row, after the family rows, before the CONTINUE

        def rname(i: int) -> str:
            if cont and i == N - 1:
                return "CONTINUE"
            if N0 <= i < N0 + n_spec:
                return "SPECIAL " + spec.entry[i - N0].id
            if N0 + n_spec <= i < N0 + n_spec + n_hop:
                return hop[1][i - N0 - n_spec]
            if D0 <= i < D0 + n_ds:
                return ds.names[i - D0]
            if n_map and i == M0:
                return "SPECIAL MAP"
            return cs.name(i)
        # map v2 M4d2 (only with SSBOT_FORUM_MAP2: ssbot.map2.live.Map2Controller.hold_row sets it; None otherwise and
        # nothing below changes): the bridge this planner sent while map2's search from it runs - the CONTINUE row is
        # that bridge (its frames from f + 2, aligned by the frames actually elapsed) and ranks first among the safe
        # rows (below every safety key), so the fallback follows it unless its own checks need a change
        hold_row = getattr(self, "hold_row", None)
        hold_on = hold_row is not None and cont
        if cont:
            rows_.append((cmod.continue_plan(self.prev_cmd, 1, T) if not hold_on else
                          _hold_pad(hold_row, T))[None])
        cmd = np.concatenate(rows_)
        rem0 = self.jump_until - self.ticks
        if rem0 > 0:
            att = np.array([n.startswith("ATTACK") for n in cs.first_names])[cs.first]
            if att.any():
                cmd = cmd.copy()
                cmd[:N0][att, :min(rem0, T)] |= B_JUMP
        N = len(cmd)
        core = np.concatenate([core0, np.zeros(n_spec + n_ds + n_map + int(cont), bool)]) if not n_hop else \
            np.concatenate([core0, np.zeros(n_spec, bool), np.ones(n_hop - n_chase, bool), np.zeros(n_chase, bool),
                            np.zeros(n_ds + n_map + int(cont), bool)])
        win_rows_ = np.zeros(N, bool)         # task oldwin: the window rows (stage F: their own place in the order)
        if n_ds and win_ is not None and getattr(self, "_win_c", None):
            win_rows_[D0 + getattr(self, "_win_off", 0):D0 + n_ds] = True
        full = np.empty((N, P + T), np.int64)
        full[:, :P] = prefix
        full[:, P:] = cmd
        ok, why = veto(cs, ctx)
        if CL_NODOWN and SPECIAL_MAP:
            self.audit.map_nodown_ignored += 1    # SG4: the readiness penalty replaces it
        if CL_NODOWN and not SPECIAL_MAP and self._clapper_near(f, start):
            dn = (cs.prim_bits & (1 << int(cmod.Prim.ATTACK_DOWN))) != 0
            self.audit.cl_nodown += int((ok & dn).sum())
            ok = ok & ~dn
            why = np.where(dn & (why == 0), 1, why)
        sm_on = bool(v2 and special_mode.SPECIAL_MODE)
        if special_mode.SPECIAL_MODE:
            # the L2 controller reads this tick's decision (or none) next tick (review: cleared on every tick, v2 or
            # not, so no stale strike spot outlives the tick that posted it)
            special_mode.BOARD.clear()
        sctx = None
        self._sctx = None
        if n_spec and sm_on:
            # (f) the special rows on the keys they use
            kok = special_mode.row_keys_allowed(spec.cmd, ctx.allowed_mask)
            ok = np.append(ok, kok)
            why = np.append(why, np.where(kok, 0, 1))
            self.audit.sm_keys_veto += int((~kok).sum())
        elif n_spec:
            ok = np.append(ok, np.full(n_spec, bool(ctx.allowed_mask.all())))
            why = np.append(why, np.full(n_spec, 0 if ok[-1] else 1))
        if n_hop:
            okb = int(sum(1 << i for i, a_ in enumerate(ctx.allowed_mask) if a_))
            hok = (hop[2] & ~okb) == 0
            ok = np.append(ok, hok)
            why = np.append(why, np.where(hok, 0, 1))
        if n_ds:
            kok = special_mode.row_keys_allowed(ds.cmd, ctx.allowed_mask)
            ok = np.append(ok, kok)
            why = np.append(why, np.where(kok, 0, 1))
        if n_map:
            kok = special_mode.row_keys_allowed(mrow.cmd[None], ctx.allowed_mask)
            ok = np.append(ok, kok)
            why = np.append(why, np.where(kok, 0, 1))
        if cont:
            ok = np.append(ok, bool(ctx.allowed_mask.all()) or self._prev_allowed(ctx))
            why = np.append(why, 0 if ok[-1] else 1)
        latched, hold_end = hold_filter_jit(full, hold)
        t1 = time.perf_counter()
        # ---- stage 1: the nominal lane, its box centre against the support ----
        r1 = kin.rollout(start, latched, params, self.terrain, threads=cfg.threads)
        if sm_on and getattr(self, "_spec_meta", None) is not None and (n_spec or (cont and pv_sm is not None)):
            # the special mode: the special rows (and the CONTINUE of a chosen one, same enemy) get the bounce lanes,
            # the special support and their continuation's check
            s_rows, s_ext = [], []
            for q in range(n_spec):
                s_rows.append(N0 + q)
                fq = spec.full[q] if spec.full is not None else None
                s_ext.append(fq if fq is not None else spec.cmd[q])
            pv = pv_sm
            if cont and pv is not None and pv["iid"] == self._spec_meta["iid"] and len(pv["ext"]) > 1 and \
                    not pv.get("map"):
                s_rows.append(N - 1)
                s_ext.append(pv["ext"][1:])
            sctx = self._special_ctx(f, start, hold, prefix, latched, r1, np.asarray(s_rows, np.int64), s_ext, T)
            self._sctx = sctx
            if sctx is not None:
                self.audit.sm_ms += sctx.ms
        if SPECIAL_MAP and sctx is None and n_map:
            # SG4: the map row judged as a special row: the map certifies the Clapper's whole move; the others, its
            # hazards and its body outside the pre-protect frames stay (special_mode's support). Review: the CONTINUE
            # of last tick's map row is not (it kept the old anchor / move frame and the Clapper's move dropped after
            # every map exit: deviation, the move's end, an off-macro state); it keeps the full checks, and when the
            # hero followed the row this tick's map row is its continuation (MapRuntime.extend)
            tm_ = time.perf_counter()
            self._spec_meta = mrow.meta
            sctx = self._special_ctx(f, start, hold, prefix, latched, r1, np.asarray([M0], np.int64), [mrow.ext], T)
            self._sctx = sctx
            map_ms += (time.perf_counter() - tm_) * 1e3
        if n_ds and ds.lane is not None:
            # G3, the certain-hit rule: the certain family rows are judged on their bounce lane from the press on
            # (stage 1, the score, the end state for the escape)
            rc = D0 + np.flatnonzero(ds.cert)
            for nm in ("phys", "pos", "vel", "mode", "flags", "box"):
                getattr(r1, nm)[rc] = ds.lane[nm]
            r1.final[:, rc] = ds.lane["final"]
        t1r = time.perf_counter()
        T1 = P + T + 1
        tk = np.arange(T1, dtype=np.float64) * params.frame_time
        enemy_only = not any(fm.hazard for fm in f.fc.model.families.values())
        # the first frames each, then every other one: a contact found is real, so S1 stays a necessary condition;
        # a row in contact only on a skipped frame passes on to the envelope
        fr = self._s1_frames(T1)
        cx = 0.5 * (r1.box[:, fr, 0] + r1.box[:, fr, 2])
        cy = 0.5 * (r1.box[:, fr, 1] + r1.box[:, fr, 3])
        o_cm = o_f = None
        if fcfg.commit_rank and hasattr(f, "occupied_split"):
            # commit_rank's parts from the same queries (the union is occupied()'s array): no work after the envelope
            o, o_cm, o_f = f.occupied_split(cx, cy, tk[fr])
        else:
            o = f.occupied(cx, cy, tk[fr])
        o = self._v2_dash(o, f, r1, cx, cy, tk[fr], fr)
        map_x = bool(o[M0].any()) if n_map else None   # SG4's cross-check: the full support on the map row (not a veto)
        if sctx is not None:
            # (a, b) the special rows on stage 1: their bounce lane against the special support
            sr = sctx.rows
            o[sr] = special_mode.occ_special(sctx, f.rs, np.arange(len(sr)), cx[sr], cy[sr], tk[fr])
        if enemy_only:
            o &= (r1.flags[:, fr] & F_INVULN) == 0
        S1 = o.any(axis=1)
        # the first contact's estimate for FORCED_RISK's preselection: at stage 1 its lower bound (the frame after the
        # last clear sampled one), on the envelope its first frame, with the hit branch the earlier of the two
        k1 = o.argmax(axis=1)
        t_hit = np.where(S1, np.where(k1 > 0, fr[np.maximum(k1 - 1, 0)] + 1, fr[0]), T1)
        t2 = time.perf_counter()
        sc = self._score_forum(ws, r1, latched, start, f, prefs, tk, ctx)
        J = sc["J"]
        if sctx is not None:
            # (b) a down slash on an enemy in a move is a certain hit: a special row's strike (its contact with E's
            # move boxes) counts as one landed hit on E where the scorer's target boxes missed it (the hit term at
            # E's hit weight; none while the controller gives E none)
            hw_e = float((getattr(prefs, "hit_w", None) or {}).get(sctx.iid, 0.0))
            miss_ = sctx.rows[np.asarray(sc["nh"])[sctx.rows] < 1.0]
            if len(miss_) and hw_e > 0:
                J[miss_] += prefs.weights.get("hit", 10.0) * hw_e
                for k_ in ("nh", "hits"):
                    if k_ in sc:
                        sc[k_] = np.asarray(sc[k_], np.float64).copy()
                        sc[k_][miss_] = np.maximum(sc[k_][miss_], 1.0)
                self.audit.sm_hit_credit += len(miss_)
        if n_ds and ds.extra.any():
            # G3: a certain second strike past the horizon (the scorer cannot see it) counts as a landed hit
            hw_ = getattr(prefs, "hit_w", None) or {}
            for q in np.flatnonzero(ds.extra):
                r_ = D0 + int(q)
                J[r_] += prefs.weights.get("hit", 10.0) * float(hw_.get(int(ds.tgt[q]), 1.0))
                for k_ in ("nh", "hits"):
                    sc[k_] = np.asarray(sc[k_], np.float64)
                    sc[k_][r_] += 1.0
            self.audit.ds_credit += int(ds.extra.sum())
        tac = fcfg.tac
        P1 = o.mean(axis=1) if len(fr) else np.zeros(N)
        if "eml" in tac:
            # the effective mask loss (the person, 2026-10-08: 9 silk heal 3 masks, 4 hits landed = 1 mask): the
            # stage-1 share in contact x the masks a contact costs, priced at hits_per_mask hit weights a mask (the
            # hits themselves are the hit term already); safe rows have no stage-1 contact: 0
            J -= fcfg.eml_hits_per_mask * prefs.weights.get("hit", 10.0) * fcfg.eml_mask * P1
        if cont:
            J[-1] += prefs.weights.get("cont", 0.0)
        unm = sc["unmod"] & ok
        why[unm] = R_UNMOD
        ok &= ~sc["unmod"]
        hz = np.zeros(N, bool)
        hz_soft = np.zeros(N, bool)
        if ctx.hazards or ctx.soft:
            hull, kfl = knockback_hull(r1.box, params, self.terrain, threads=cfg.threads)
            hz, hz_soft = hazard_flags(hull, kfl, ctx)
        may_kill, k_lo, k_hi, in_flight = kill_frames(latched, r1.flags, r1.mode, P, ctx)
        # the Forum's final kill is not certified in R3 (no kill branches): it passes only under I3
        U = unpausable(may_kill | in_flight, ctx, None)
        veto_k = U & may_kill
        if veto_k.any():
            why[ok & veto_k] = R_KILL
            ok = ok & ~veto_k
        t3 = time.perf_counter()
        # ---- stage 2: the envelope, in priority order, with the deadline ----
        S = S1.copy()
        env = np.zeros(N, bool)
        bound = r1.box.copy()
        tg_ = sc["targets"]
        # rows whose first predicted hit is a bell (bell_hits): knocking it back is a defence (the hit branch drops it),
        # so a row in contact at stage 1 whose swing meets a bell first goes on to the envelope and that branch
        bell_first = np.array([0 <= int(t) < len(tg_) and bool(tg_[int(t)].hazard) for t in sc["first_t"]], bool) \
            if self.fcfg.bell_hits and any(t.hazard for t in tg_) else np.zeros(N, bool)
        pass1 = ok & (~S1 | (bell_first & (sc["first_f"] <= t_hit)))
        pre = np.lexsort((-J, U, hz_soft, hz))
        pre = pre[pass1[pre]]
        kr = None
        if special_mode.KEEP and getattr(self, "_kp", None) is not None:
            # G4 4b: the kept template's row this tick: the special CONTINUE still certified with a contact (in
            # sctx.rows), or the family's "DS cont" whose contact still holds; none: it is gone
            if self._kp == "sm" and sctx is not None and cont and (N - 1) in set(sctx.rows.tolist()):
                kr = N - 1
            elif self._kp == "ds" and n_ds:
                # a kept chain while both its presses are ahead: its "+c<b>" twin (both bounces on its lane, the
                # second press inside the horizon or past it; review2: never the plain "DS cont", whose lane has no
                # second bounce); one press left (or a kept single strike): "DS cont"
                kb = getattr(self, "_ds_keep_b", None)
                pv_ = getattr(self, "_ds_prev", None)
                a_on = (np.asarray(pv_ if pv_ is not None else (), np.int64) & B_ATTACK) != 0
                n_ahead = int((a_on[1:] & ~a_on[:-1]).sum()) if len(a_on) > 1 else 0
                nm_ = f"DS cont+c{kb}" if (kb is not None and n_ahead >= 2) else "DS cont"
                kr = D0 + ds.names.index(nm_) if nm_ in ds.names else None
            self.audit.kp_ticks += 1
            if kr is None:
                # done (the kept plan's press is under way or none is left: the template ran out) or gone (its row
                # lost its contact / certified press while a press is still ahead, or the enemy left the move)
                pl_ = np.asarray((pv_sm or {}).get("ext", ()) if self._kp == "sm" else
                                 (getattr(self, "_ds_prev", None) if getattr(self, "_ds_prev", None) is not None
                                  else ()), np.int64)
                a_on = (pl_ & B_ATTACK) != 0
                rise = a_on & ~np.concatenate([[False], a_on[:-1]]) if len(pl_) else a_on
                done = (not len(pl_)) or bool(a_on[0]) or not rise[1:].any()
                self.audit.kp_done += int(done)
                self.audit.kp_sw_gone += int(not done)
        hf = bool(special_mode.HITS_FIRST and v2 and (sctx is not None or n_ds))
        hf_h = None
        hf_ok_: dict = {}               # review2: the tier rows' escape results {row: (failures, labels, ESC_TAIL's first)}
        if hf:
            # G4 4c (the person: most hits first, stop early): the strike options (special rows, family rows) that
            # passed stage 1 are enveloped first, the kept template's row alone first, then by their hit count (the
            # scorer's landed hits after the certain-hit credits; MOVE_HITS: on the move's path), J within a count;
            # once a count's rows include one passing every check (the escape check too), the rows with fewer hits
            # are not enveloped
            hk = np.floor(np.asarray(sc["nh"], np.float64) + 1e-9).astype(np.int64)
            strike = np.zeros(N, bool)
            if sctx is not None:
                strike[sctx.rows] = True
            if n_ds:
                strike[D0:D0 + n_ds] = True
            hf_rows = [int(i) for i in pre if strike[i]]
            hf_rows.sort(key=lambda i: -hk[i])
            if kr is not None and kr in hf_rows:
                hf_rows.remove(kr)
                hf_rows.insert(0, kr)
            hf_bounds = set()
            for p_, i in enumerate(hf_rows):
                nx_ = hf_rows[p_ + 1] if p_ + 1 < len(hf_rows) else None
                if nx_ is None or (p_ == 0 and i == kr) or hk[nx_] != hk[i]:
                    hf_bounds.add(p_ + 1)
            hf_t0 = 0
            self.audit.hf_ticks += int(bool(hf_rows))
            rem_ = self.jump_until - self.ticks
            hf_keep = np.ones(N, bool)
            if rem_ > 0:
                wj_ = cmd[:, :min(rem_, T, cfg.release_latency)]
                hf_keep = ((wj_ & B_JUMP) != 0).all(axis=1) & ((wj_ & B_QUICKCAST) == 0).all(axis=1)
            hf_mkeep = np.ones(N, bool)
            if cont and self.macro_until > self.ticks:
                hf_mkeep = J >= J[N - 1] + MACRO_MARGIN
                hf_mkeep[N - 1] = True
            # the rows the dash focus sets S = 1 at the selection (v2_dash_only) never pass
            dd_ = getattr(self, "v2_dash_only", None)
            if dd_ is not None and len(dd_) and forum_v2.FOCUS_DASH == "1":
                hf_keep = hf_keep.copy()
                hf_keep[dd_] = False
            prio = hf_rows + [int(i) for i in pre[core[pre] & ~strike[pre]]]
            n_core = len(prio)
        else:
            core_rows = pre[core[pre]]
            prio = [int(i) for i in core_rows]
            n_core = len(prio)
            if sctx is not None:
                # the special mode: the special rows that passed stage 1 are always enveloped (after the core rows)
                prio += [int(i) for i in sctx.rows if pass1[i] and int(i) not in prio]
                n_core = len(prio)                    # (as the core rows: not cut by the deadline)
            if n_ds:
                # G3: the family rows that passed stage 1 are always enveloped (after the core and special rows);
                # stage F: the window rows (task oldwin) only with SSBOT_FORUM_WINDOWS_CORE=1 - by default they come
                # after every row of the old order below (cut by the deadline)
                prio += [D0 + q for q in range(n_ds) if pass1[D0 + q] and (D0 + q) not in prio and
                         (WIN_CORE or not win_rows_[D0 + q])]
                n_core = len(prio)
        if cont and pass1[N - 1] and not core[N - 1] and (N - 1) not in prio:
            prio.append(N - 1)
        if hold_on and pass1[N - 1] and not hf:
            # M4d2: the held bridge is enveloped first and never cut by the deadline (its own checks decide the hold;
            # a busy tick otherwise left it unchecked - not safe - and the hold broke)
            if (N - 1) in prio[:n_core]:
                prio.remove(N - 1)
                prio.insert(0, N - 1)
            else:
                if (N - 1) in prio:
                    prio.remove(N - 1)
                prio.insert(0, N - 1)
                n_core += 1
        rest = [int(i) for i in pre if not core[i] and not (cont and i == N - 1) and not win_rows_[i]]
        top = rest[:fcfg.K_b]
        # review (SG4): the map row counted too (without it a tick with no CONTINUE whose map row passed stage 1 raised
        # IndexError; with a CONTINUE the map row read the CONTINUE's slot)
        first = np.concatenate([cs.first, np.full(n_spec + n_hop + n_ds + n_map + int(cont), -1, cs.first.dtype)])
        sib = []
        top_set = set(top)
        by_first: dict = {}
        for j in rest:
            by_first.setdefault(int(first[j]), []).append(j)
        for i in rest[:8]:
            if first[i] < 0:
                continue
            sib += [j for j in by_first[int(first[i])] if j != i and j not in top_set][:fcfg.sibs]
        seen = set(prio)
        for i in top + sib:
            if i not in seen:
                prio.append(i)
                seen.add(i)
        if win_rows_.any():
            # stage F: the window rows that passed stage 1 after the old order's rows (enveloped while time remains)
            for i in pre:
                if win_rows_[i] and pass1[i] and int(i) not in seen:
                    prio.append(int(i))
                    seen.add(int(i))
        n_prio = len(prio)
        queue = prio + [i for i in rest if i not in seen]
        budget = {"hitfx": 0, "react": 0, "capped": 0, "react_cache": {}}
        pins = self._pin_threats(f, tk) if fcfg.pin_aim else []
        self.audit.pin_ticks += int(bool(pins))
        has_hit = sc["first_f"] >= 0
        sc_ds, ds_lost = sc, None
        if n_ds and ds.cert.any():
            # review2: every certain family row gets its hit branch, anchored at its certain contact
            sc_ds, rc_, ds_lost = self._ds_anchor(sc, ds, D0, r1, latched,
                                                  1 if np.asarray(start).reshape(kin.K, -1)[kin.FACE, 0] >= 0 else -1)
            has_hit = has_hit.copy()
            has_hit[rc_] = True
        sp_e = None
        if sctx is not None:
            # review: the special rows whose first predicted hit is on E (or none) skip the hit branch (the bounce is
            # their hit); one whose first hit is another enemy runs it against the full support (that enemy's
            # reaction is not certified by E's table)
            sp_e = np.zeros(N, bool)
            tg_ = sc["targets"]
            for r_ in sctx.rows:
                r_ = int(r_)
                if sc["first_f"][r_] < 0 or (len(tg_) and getattr(tg_[int(sc["first_t"][r_])], "iid", None) == sctx.iid):
                    sp_e[r_] = True
            self.audit.sm_hit_other += int(len(sctx.rows) - sp_e[sctx.rows].sum())
        hit_occ: dict = {}                        # row -> its hit branch's contact [T1] (FORCED_RISK's ranking)
        capped_rows: list = []                    # rows S = 1 by a cap only (checked uncapped before FORCED_RISK)
        safe_any = False
        pos = 0
        overrun = False
        cut = False
        chunk_ms = 0.0
        while pos < len(queue):
            tc0 = time.perf_counter()
            end_ = pos + fcfg.chunk
            if hf and hf_h is None:
                nb_ = [b_ for b_ in hf_bounds if b_ > pos]
                if nb_:
                    end_ = min(end_, min(nb_))        # a chunk never crosses a hit count's end
            ch = np.array(queue[pos:end_], np.int64)
            pos += len(ch)
            m_sp = np.isin(ch, sctx.rows) if sctx is not None else None
            m_ds = None
            if n_ds and ds.lane is not None:
                w_ = (ch >= D0) & (ch < D0 + n_ds)
                m_ds = np.zeros(len(ch), bool)
                m_ds[w_] = ds.cert[ch[w_] - D0]
                m_ds = m_ds if m_ds.any() else None
            if (m_sp is not None and m_sp.any()) or m_ds is not None:
                evc = np.zeros((len(ch), latched.shape[1]), np.int64)
                if m_sp is not None and m_sp.any():
                    q_sp = np.searchsorted(sctx.rows, ch[m_sp])
                    evc[m_sp] = sctx.ev[q_sp]
                else:
                    m_sp = None
                if m_ds is not None:
                    evc[m_ds] = ds.ev[ch[m_ds] - D0]      # G3: the certain family rows on their bounce lanes
                r2 = kin.rollout(start, latched[ch], params, self.terrain, events=evc, variants=fcfg.variants,
                                 threads=cfg.threads)
            else:
                m_sp = None
                r2 = kin.rollout(start, latched[ch], params, self.terrain, variants=fcfg.variants, threads=cfg.threads)
            skip = ((r2.flags_all & F_INVULN) != 0) if enemy_only else np.zeros(r2.flags_all.shape, bool)
            occ = self._contacts(f, r2.bound, tk, skip)
            if m_sp is not None:
                # (a, b) the special rows' envelope: the bounce lanes against the special support (the full support
                # from a row's full_from on)
                o_sp = self._contacts_fn(f, r2.bound[m_sp], tk, skip[m_sp],
                                         lambda X, Y: f.rs.occ_stack_b(sctx.st_o, X, Y, tk))
                o_b = self._contacts_fn(f, r2.bound[m_sp], tk, skip[m_sp],
                                        lambda X, Y: f.rs._occ_stack(sctx.st_b, X, Y, tk))
                o_sp |= o_b & ~special_mode.pre_protect(sctx, q_sp, np.arange(T1))
                ff = sctx.full_from[q_sp]
                if (ff < T1).any():
                    late = np.arange(T1)[None, :] >= ff[:, None]
                    o_sp = np.where(late, occ[m_sp], o_sp)
                occ[m_sp] = o_sp
            s2 = occ.any(axis=1)
            if ds_lost is not None and len(ds_lost):
                s2 = s2 | np.isin(ch, ds_lost)       # review2: a certain row whose hit branch cannot be anchored
            S[ch] = s2
            env[ch] = True
            bound[ch] = r2.bound
            t_hit[ch] = np.where(s2, occ.argmax(axis=1), T1)
            hr = ch[~s2 & has_hit[ch]] if m_sp is None else ch[~s2 & has_hit[ch] & ~(m_sp & sp_e[ch])]
            if bell_first.any():
                # in contact, but the swing meets a bell first: the branch with the bell knocked back decides
                hb_ = ch[s2 & bell_first[ch] & (sc["first_f"][ch] <= t_hit[ch])]
                if len(hb_):
                    budget["hitfx"] += len(hb_)
                    sh, oh, cp = self._hit_branch(f, start, latched, sc, hb_, tk, enemy_only, budget)
                    S[hb_] = sh
                    t_hit[hb_] = T1
                    self._note_hit(hb_, sh, oh, cp, sc, t_hit, hit_occ, capped_rows, T1)
            hr_ds = None
            if n_ds and len(hr):
                # G3: the family rows' hit branches are outside the hit-branch cap (the family is the point of the
                # tick when it runs; its rows are at most dslash.MAX_ROWS)
                isd = (hr >= D0) & (hr < D0 + n_ds)
                hr_ds, hr = hr[isd], hr[~isd]
            if hr_ds is not None and len(hr_ds):
                budget["hitfx_ds"] = budget.get("hitfx_ds", 0) + len(hr_ds)      # (the other rows' room unchanged)
                isw_ = win_rows_[hr_ds]
                for grp_, cap_ in ((hr_ds[~isw_], True), (hr_ds[isw_], WIN_CORE_CAP)):
                    if not len(grp_):
                        continue
                    # stage F: the window rows (enveloped after the old order) get their hit enemy's reaction checked
                    # outside the reaction cap and without spending it (the old rows' budget as in h2)
                    r0_ = budget["react"]
                    sh, oh, cp = self._hit_branch(f, start, latched, sc_ds, grp_, tk, enemy_only, budget, cap=cap_,
                                                  ev_base=self._ds_evb(grp_, D0, ds))
                    if not cap_:
                        budget["react"] = r0_
                    S[grp_] |= sh
                    self._note_hit(grp_, sh, oh, cp, sc_ds, t_hit, hit_occ, capped_rows, T1)
            if len(hr):
                room = fcfg.hitfx_k - budget["hitfx"]
                over = hr[max(room, 0):]
                hr = hr[:max(room, 0)]
                if len(over):
                    S[over] = True
                    budget["capped"] += len(over)
                    capped_rows += [int(i) for i in over]
                    for i in over:                # unknown from the hit frame on: in contact from there (ranking)
                        h = np.zeros(T1, bool)
                        h[max(int(sc["first_f"][i]), 1):] = True
                        hit_occ[int(i)] = h
                        t_hit[i] = min(int(t_hit[i]), int(np.argmax(h)))
                if len(hr):
                    budget["hitfx"] += len(hr)
                    sh, oh, cp = self._hit_branch(f, start, latched, sc, hr, tk, enemy_only, budget,
                                                  ev_base=self._ds_evb(hr, D0, ds))
                    S[hr] |= sh
                    self._note_hit(hr, sh, oh, cp, sc, t_hit, hit_occ, capped_rows, T1)
            if pins:
                # the aimed pins (pin_aim): a row still safe meets a pin the Reed will throw at where the row is then
                pr = ch[~S[ch]]
                if len(pr):
                    pk = self._pin_contacts(pins, r1, pr, tk, enemy_only)
                    S[pr[pk >= 0]] = True
                    t_hit[pr[pk >= 0]] = pk[pk >= 0]
                    self.audit.pin_rows += int((pk >= 0).sum())
            if v2 and f.rs.pend:
                # v2: the pending aims (forum_v2.RangeSupport.aim_fail) on the nominal lane of the rows still safe
                pr = ch[~S[ch]]
                if len(pr):
                    if m_sp is None:
                        af = f.rs.aim_fail(0.5 * (r1.box[pr, :, 0] + r1.box[pr, :, 2]),
                                           0.5 * (r1.box[pr, :, 1] + r1.box[pr, :, 3]), self._v2_locked(r1, pr))
                    else:
                        # the special rows: E's own aims skipped (the special mode drops its move's aim zones)
                        af = np.zeros(len(pr), bool)
                        isp = np.isin(pr, sctx.rows)
                        for msk, skip_iid in ((~isp, None), (isp, sctx.iid)):
                            if msk.any():
                                pp = pr[msk]
                                af[msk] = f.rs.aim_fail(0.5 * (r1.box[pp, :, 0] + r1.box[pp, :, 2]),
                                                        0.5 * (r1.box[pp, :, 1] + r1.box[pp, :, 3]),
                                                        self._v2_locked(r1, pp), skip_iid=skip_iid)
                    S[pr[af]] = True
                    t_hit[pr[af]] = np.minimum(t_hit[pr[af]], T1 - 1)
                    self.audit.v2_aim_rows += int(af.sum())
            safe_now = bool((env & ok & ~S & ~hz).any())
            safe_any = safe_any or safe_now
            if hf and hf_h is None and pos in hf_bounds:
                # G4 4c: this hit count's rows done: one passing every check (S, hazards, unpausable, the committed
                # hold, the macro margin, the v2 escape) -> the rest of the queue keeps only rows with as many hits
                tier = [i for i in queue[hf_t0:pos] if ok[i] and env[i] and not S[i] and not hz[i] and not hz_soft[i]
                        and not U[i] and hf_keep[i] and hf_mkeep[i]]
                hf_t0 = pos
                if tier:
                    if not hasattr(self, "_v2_esc_first"):
                        self._v2_esc_first = {}
                    nf_, lb_ = self._escape_fail_v2(f, r1, hold_end, np.asarray(tier, np.int64))
                    e1_ = getattr(self, "_v2_esc_first", {})
                    hf_ok_.update({int(r_): (int(n_), l_, e1_.get(int(r_))) for r_, n_, l_ in zip(tier, nf_, lb_)})
                    if (nf_ == 0).any():
                        hf_h = int(hk[tier[int(np.argmax(nf_ == 0))]])
                        rest_q = queue[pos:]
                        keep_q = [i for i in rest_q if hk[i] >= hf_h]
                        drop_q = [i for i in rest_q if hk[i] < hf_h]
                        a_ = self.audit
                        a_.hf_stop += 1
                        a_.hf_stop2 += int(hf_h >= 2)
                        a_.hf_skipped += len(drop_q)
                        a_.hf_skipped_strike += int(strike[drop_q].sum()) if drop_q else 0
                        core_set = set(queue[:n_core])
                        prio_set = set(queue[:n_prio])
                        queue = queue[:pos] + keep_q
                        n_core = pos + sum(1 for i in keep_q if i in core_set)
                        n_prio = pos + sum(1 for i in keep_q if i in prio_set)
            now = time.perf_counter()
            chunk_ms = (now - tc0) * 1e3
            if pos >= n_core and safe_any:
                if pos >= n_prio:
                    break
                # the next chunk would end past the deadline (it costs about what this one did): stop before it
                if (now - t0) * 1e3 - (map_ms if MAP_DL_SHIFT else 0.0) + chunk_ms > fcfg.deadline_ms:
                    cut = pos < len(queue)
                    break
            el_ms = (time.perf_counter() - t0) * 1e3 - (map_ms if MAP_DL_SHIFT else 0.0)
            if not safe_any and el_ms > fcfg.deadline_ms and pos < len(queue):
                overrun = True
        if not safe_any and capped_rows:
            # no safe row: the rows a cap set S = 1 get their hit branch uncapped, so FORCED_RISK never depends on the
            # caps (whose order follows J and so the prefs: §4.4 item 2's "goal FORCED_RISK => default FORCED_RISK")
            cr = np.array(sorted(set(capped_rows)), np.int64)
            cr = cr[ok[cr] & ~hz[cr]]
            if len(cr):
                sh, oh, cp = self._hit_branch(f, start, latched, sc_ds, cr, tk, enemy_only, budget, cap=False,
                                              ev_base=self._ds_evb(cr, D0, ds))
                S[cr] = sh
                t_hit[cr] = T1
                self._note_hit(cr, sh, oh, cp, sc_ds, t_hit, hit_occ, [], T1)
                budget["uncapped"] = len(cr)
        clash_p = np.zeros(N)
        clash_n = np.zeros(N, np.int64)
        clash_w = np.zeros(N)
        clash_occ: dict = {}                      # row -> (w, its clash branch's contact [T1] or None: clean)
        self._clash_inv = {}
        self._clash_fams = {}
        if fcfg.clash and fcfg.clash_branch and not v2 and not (env & ok & ~S & ~hz).any():
            # no safe row: the clash branch (the plan's "成功率高的招不再逼出 FORCED_RISK"); plain safe rows always
            # come first, so it never runs on a tick that has one
            self.audit.clash_ticks += 1
            tcl = time.perf_counter()
            cl = self._clash_pass(f, start, latched, sc, S, ok, hz, tk, enemy_only, ctx, t_hit,
                                  t0 + (map_ms * 1e-3 if MAP_DL_SHIFT else 0.0))
            self.audit.clash_ms += (time.perf_counter() - tcl) * 1e3
            for i, (w, ph, nc, tn, oc) in cl.items():
                clash_n[i] = nc
                clash_w[i] = w
                if oc is None and w >= fcfg.clash_min_p and ph <= fcfg.clash_max_fail:
                    S[i] = False
                    env[i] = True
                    t_hit[i] = T1
                    # after the plain safe rows: by how likely it fails (main: the hit-anyway bound, never 0)
                    clash_p[i] = max(ph, 1e-6) if fcfg.clash_main else 1.0 - w
                    self.audit.clash_rows += 1
                    if "whip" in tac and any(fm in WHIP_FAMS for fm in self._clash_fams.get(i, ())):
                        # the person (DESIGN 3.5.6, 2026-10-08): clashing the whip is safe but gains nothing: no hit
                        # credit, w_whip_clash hits off (behind it / another target score instead)
                        J[i] -= prefs.weights.get("hit", 10.0) * (float(sc["hits"][i]) + fcfg.w_whip_clash)
                        self.audit.whip_clash_rows += 1
                else:
                    # in contact after its clashes (another enemy's support, an attack it cannot clash), or clean but
                    # not likely enough: S = 1; FORCED_RISK ranks it by w x the branch's share + (1 - w) x the plain
                    # row's (its first contacts stay the plain row's)
                    clash_occ[i] = (w, oc)
                    self.audit.clash_partial += 1
        t4 = time.perf_counter()
        dash_only = getattr(self, "v2_dash_only", None)
        if dash_only is not None and len(dash_only) and forum_v2.FOCUS_DASH == "1":
            S = S.copy()
            S[dash_only] = True
        known = env | S1
        safe = ok & env & ~S & ~hz
        self.last_safe, self.last_cs = safe, cs
        V = np.zeros(N, bool)
        counts = np.bincount(first[:N0][safe[:N0]], minlength=len(cs.first_names))
        if n_hop > n_chase:
            self.audit.hop_ticks += 1
            self.audit.hop_rows += n_hop - n_chase
            self.audit.hop_safe += int(safe[N0 + n_spec:N0 + n_spec + n_hop - n_chase].sum())
        if n_chase:
            self.audit.chase_ticks += 1
            self.audit.chase_rows += n_chase
            self.audit.chase_safe += int(safe[N0 + n_spec + n_hop - n_chase:N0 + n_spec + n_hop].sum())
        if n_spec:
            self.audit.spec_ticks += 1
            self.audit.spec_rows += n_spec
            self.audit.spec_safe += int(safe[N0:N0 + n_spec].sum())
        if sctx is not None:
            a_ = self.audit
            a_.sm_ticks += 1
            a_.sm_rows += len(sctx.rows)
            a_.sm_long += int(sctx.is_long.sum())
            a_.sm_tail_ok += int(sctx.tail_ok.sum())
            ns_ = int(safe[sctx.rows].sum())
            a_.sm_safe += ns_
            a_.sm_safe_ticks += int(ns_ > 0)
        if n_ds:
            a_ = self.audit
            ns_ = int(safe[D0:D0 + n_ds].sum())
            a_.ds_safe += ns_
            a_.ds_safe_ticks += int(ns_ > 0)
        V[:N0] = counts[first[:N0]] >= 2
        if cont:
            V[-1] = safe[-1]
        rem = self.jump_until - self.ticks
        keep = np.ones(N, bool)
        if rem > 0:
            wj = cmd[:, :min(rem, T, cfg.release_latency)]
            keep = ((wj & B_JUMP) != 0).all(axis=1) & ((wj & B_QUICKCAST) == 0).all(axis=1)
        bind_res = None
        self.last_sel = None
        esc_tail = None
        self._v2_esc_first = {}
        rxl_ = None                           # SSBOT_FORUM_TWO_RUNEEXIT: the safe rows late for a circle's exit
        if prefs.want_bind and ctx.want_bind:
            bind_res = self._bind(ws, start, hold, prefix, f, ctx)
        forced = not safe.any() and not (bind_res is not None and bind_res[0])
        Pc = np.zeros(N)
        t_c = np.full(N, T1, np.int64)
        sk_n = np.zeros(N, np.int64)          # the "seen" keys (0 on every row otherwise: the order is unchanged)
        sk_f = np.full(N, T1, np.int64)
        sk_c = np.zeros(N)
        sel = ok & known
        if forced and sctx is not None:
            # review: no safe row: a special row's stage-1 share and first contact were read without M's danger, so in
            # the FORCED_RISK ranking it would look safer than it is; out (the fallback is the normal rows)
            sel[sctx.rows] = False
            self.audit.sm_forced_out += 1
        if forced and win_rows_.any() and n_ds:
            # stage F (review finding 2): the certain window rows likewise (their stage-1 share, first contact and hit
            # branch read off the bounce lane, which rises away from the target by construction); the uncertain ones
            # were judged on their own lane as any row and stay
            wc_ = np.zeros(N, bool)
            wc_[D0:D0 + n_ds] = (ds.cert | (ds.extra > 0)) & win_rows_[D0:D0 + n_ds]
            if (sel & wc_).any():
                self.audit.win_forced_out += 1
            sel[wc_] = False
        Pcm = np.zeros(N)                     # commit_rank's keys (0 on every row otherwise: the order is unchanged)
        Pf = np.zeros(N)
        eml_k = np.zeros(N)                   # track A "eml": FORCED_RISK's tie-break after the first contacts
        if forced and sel.any():
            cand = np.flatnonzero(sel)
            if fcfg.forced_rank in ("seen", "seen_cf"):
                inv1 = (r1.flags & F_INVULN) != 0
                if fcfg.clash_main and clash_occ:
                    # a row with a clash branch: the frames its parry i-frames cover are no contact (R8's note)
                    inv1 = inv1.copy()
                    for r_, m_ in getattr(self, "_clash_inv", {}).items():
                        if r_ in clash_occ and r_ < len(inv1):
                            inv1[r_] |= m_[:inv1.shape[1]]
                verts, starts, pbox, pvel = seen_polys(ws)
                if len(pbox):
                    args = (np.ascontiguousarray(r1.box, np.float64), np.ascontiguousarray(inv1), verts, starts, pbox,
                            pvel, np.ascontiguousarray(tk, np.float64), np.ascontiguousarray(cand, np.int64), 0.0)
                    cnt, fst = seen_contacts_swept(*args, self.params.frame_time, SEEN_SWEEP_MIN_U_S) \
                        if fcfg.seen_sweep else seen_contacts(*args)
                    sk_n[cand], sk_f[cand] = cnt[cand], fst[cand]
                if fcfg.seen_sweep and pins:
                    # "+s": a row meeting an aimed pin (not thrown yet) is a seen contact too
                    pk = self._pin_contacts(pins, r1, cand, tk, enemy_only)
                    hitp = pk >= 0
                    sk_n[cand[hitp]] += 1
                    sk_f[cand[hitp]] = np.minimum(sk_f[cand[hitp]], pk[hitp])
                    self.audit.pin_rows += int(hitp.sum())
                if fcfg.forced_rank == "seen_cf":
                    sk_c[cand] = committed_fine_share(f, r1.box, inv1, cand, fr, tk)
            if o_cm is not None:
                # the nominal box centre on stage 1's frames (its invulnerable ones skipped) against the committed
                # support (P_cm) and the current attacks' fine placements (states with a known entry: P_f): stage
                # 1's own query split by part (MultiForecast.occupied_split), so the keys cost two means here
                live = (r1.flags[cand][:, fr] & F_INVULN) == 0
                Pcm[cand] = (o_cm[cand] & live).mean(axis=1)
                Pf[cand] = (o_f[cand] & live).mean(axis=1)
            # the preselection: seen > the committed fine share (seen_cf) > P_cm > P_f (commit_rank) > the latest first
            # contact > J (a switched-off key is 0 on every row)
            if "eml" in tac:
                # the preselection's estimate: stage 1's share (the final order's is the ranked share Pc)
                eml_k[cand] = fcfg.eml_mask * P1[cand] - sc["nh"][cand] / fcfg.eml_hits_per_mask
            cand = cand[np.lexsort((-J[cand], eml_k[cand], -t_hit[cand], Pf[cand], Pcm[cand], sk_c[cand],
                                    -sk_f[cand], sk_n[cand]))]
            n_k = min(fcfg.p_k, len(cand))
            # the rows with a clash branch are ranked whatever their first contact (their branch is the point)
            pre = cand[:n_k]
            pset = set(int(i) for i in pre)
            pre = np.concatenate([pre, np.array(sorted(i for i in clash_occ if sel[i] and i not in pset),
                                                np.int64)]).astype(np.int64)
            if not fcfg.p_all:                    # p_all (audits): P for every allowed known row, the choice in pre
                cand = pre
            # the candidates on one lane over one frame set: the nominal box's centre against the support on stage
            # 1's frames (its exact test, known for every row), or'ed with the hit branch's contact there (its hull;
            # from the hit frame on where a cap left it unchecked): the share of those frames in contact and the
            # first contact's lower bound (another support query for the skipped frames cost 0.7 ms p50 on wave 6)
            on = o[cand].copy()
            for m, i in enumerate(cand):
                h = hit_occ.get(int(i))
                if h is not None:
                    on[m] |= h[fr]
            kc = on.argmax(axis=1)
            t_c[cand] = np.where(on.any(axis=1), np.where(kc > 0, fr[np.maximum(kc - 1, 0)] + 1, fr[0]), T1)
            if fcfg.exact_p:
                b = r1.box[cand]
                Pc[cand] = f.prob(0.5 * (b[..., 0] + b[..., 2]), 0.5 * (b[..., 1] + b[..., 3]), tk)
            else:
                Pc[cand] = on.mean(axis=1)
            for m, i in enumerate(cand):
                if int(i) in clash_occ:
                    w, oc = clash_occ[int(i)]
                    Pc[i] = clash_mix(w, 0.0 if oc is None else float(oc[fr].mean()), float(Pc[i]))
            if "eml" in tac:
                # the person's exchange: a row's expected masks lost (P x masks) against its hits landed / 4
                eml_k[cand] = fcfg.eml_mask * Pc[cand] - sc["nh"][cand] / fcfg.eml_hits_per_mask
            sel = np.zeros(N, bool)
            sel[pre] = True
        zero = ~cmd.any(axis=1)
        idle_clear = int(min(t_hit[zero & known].min() if (zero & known).any() else T1, T1) - P) \
            if zero.any() else None
        t5 = time.perf_counter()
        a = self.audit
        esc_info: dict = {}
        a.ticks += 1
        a.rows_enveloped += int(env.sum())
        a.rows_stage1 += N
        a.hit_branches += budget["hitfx"]
        a.reactions += budget["react"]
        a.capped += budget["capped"]
        a.uncapped_ticks += int(budget.get("uncapped", 0) > 0)
        a.uncapped_rows += budget.get("uncapped", 0)
        a.overrun += int(overrun)
        a.deadline_cut += int(cut)
        a.core_not_enveloped += int((core & pass1 & ~env).sum())
        if bind_res is not None and bind_res[0]:
            sel_cmd = self.bind.cmd[0]
            res = PlanResult(int(sel_cmd[0]), -2, "BIND", 0, False, 0.0, 1e3, True, n=N + 1,
                             n_allowed=int(ok.sum()) + 1, n_safe=int(safe.sum()) + 1, cmd=sel_cmd, path=bind_res[1])
        elif sel.any():
            mkeep = np.ones(N, bool)
            if cont and self.macro_until > self.ticks:
                mkeep = J >= J[N - 1] + MACRO_MARGIN
                mkeep[N - 1] = True
            # FORCED_RISK: the least share in contact, the latest first contact on the nominal lane, then on the
            # envelope (rows clear on the nominal lane), J (a tick with a safe row: those rows all tie on these)
            # v2: of the safe rows, the most landed hits on real enemies, then the earliest first hit (0 on every row
            # otherwise and on every unsafe row: the order is unchanged)
            v2_nh = np.where(safe, -sc["nh"], 0.0) if v2 else np.zeros(N)
            dg_pen, dg_corner = None, None          # (diagnostics: last_sel)
            if SPECIAL_MAP and v2 and self._map is not None:
                # SG4: the readiness penalty (landed-hit units) before a slam can start; rows with no safe
                # continuation from their end last (unless every row has none)
                # review: the safe rows only (the penalty ranks only those; ~half the cost)
                tm_ = time.perf_counter()
                rp_ = self._map.readiness(f, start, r1, cmd, P, self.ticks, rows=np.flatnonzero(safe))
                map_ms += (time.perf_counter() - tm_) * 1e3
                if rp_ is not None:
                    pen_ = rp_[0]
                    dg_pen = pen_
                    if CHASE:
                        # SG5: the readiness as a tier above the landed hits: the safe rows whose end leaves less
                        # than R_ref (a slam starting then: two strikes with full clearance) after the others; no
                        # safe continuation (-inf) last
                        R_ = rp_[1]
                        ref_ = float(self._map.runtime().ready_ref) if self._map.runtime() is not None else 3.0
                        je_ = getattr(self._map, "ready_j", None)        # review: the readiness's index (the evade's
                        je_ = -1 if je_ is None else int(je_)             # end while it evades)
                        low_ = chase_tier_low(R_, safe, 0.5 * (r1.box[:, je_, 0] + r1.box[:, je_, 2]),
                                              getattr(self._map, "ready_cx", None), ref_)
                        b0t_ = int(np.lexsort((-J, v2_nh + np.where(safe, pen_, 0.0)))[0]) if safe.any() else -1
                        pen_ = pen_ + np.where(low_, CHASE_TIER, 0.0)
                        b1t_ = int(np.lexsort((-J, v2_nh + np.where(safe, pen_, 0.0)))[0]) if safe.any() else -1
                        self.audit.chase_tier_ticks += 1
                        self.audit.chase_tier_rows += int(low_.sum())
                        self.audit.chase_tier_changed += int(b0t_ != b1t_)
                        dg_pen = pen_
                    b0_ = int(np.lexsort((-J, v2_nh))[0]) if safe.any() else -1
                    v2_nh = v2_nh + np.where(safe, pen_, 0.0)
                    self.audit.ready_ticks += 1
                    self.audit.ready_out_rows += int((pen_ >= 100.0).sum())
                    b1_ = int(np.lexsort((-J, v2_nh))[0]) if safe.any() else -1
                    self.audit.ready_changed += int(b0_ != b1_)
                    if self._map.ready_info is not None:
                        self._map.ready_info["changed"] = bool(b0_ != b1_)
            if v2:
                # the Clapper's corner (forum_v2.corner_zones): safe rows ending in it after the others
                zones = forum_v2.corner_zones(f)
                if zones:
                    end = r1.box[:, -1, :]
                    cxe = 0.5 * (end[:, 0] + end[:, 2])
                    cye = 0.5 * (end[:, 1] + end[:, 3])
                    corner = np.zeros(N, bool)
                    for x0, x1 in zones:
                        corner |= (cxe >= x0) & (cxe <= x1) & (cye < forum_v2.CORNER_TOP_Y)
                    v2_nh = v2_nh + np.where(safe & corner, 1000.0, 0.0)
                    self.audit.v2_corner_rows += int((safe & corner).sum())
                    dg_corner = corner
            v2_ff = np.where(safe & (sc["first_f"] >= 0), sc["first_f"], np.where(safe, T1, 0)) if v2                 else np.zeros(N, np.int64)
            nohit_ = getattr(prefs, "no_hit", None) or ()
            if v2 and nohit_ and len(sc.get("targets") or ()):
                # SSBOT_FORUM_JUMP_BEHIND (SP3): a first hit on a no_hit target does not rank (first_f itself stays:
                # the hit branch's recoil still uses it)
                tg_ = sc["targets"]
                ft_ = sc["first_t"]
                nh_ = np.array([0 <= int(t) < len(tg_) and tg_[int(t)].iid in nohit_ for t in ft_], bool)
                v2_ff = np.where(safe & nh_, T1, v2_ff)
            # SG8 (SSBOT_FORUM_SG8, forum.md 64; zeros otherwise: the order unchanged): in a Clapper slam the map
            # tracks, (a) FORCED_RISK: rows with a glide or a dash / sprint ending farther from it after the others
            # (live: glide in 3 of 8 slam hits, forced dashes into Collider 2's slope in 3), then among equal shares
            # in contact the row ending nearer the face band; (b) a safe map row this tick: rows starting a dash /
            # sprint / glide / a horizontal slash (off the map's lattice for many ticks) after the others
            fs_bad, fs_face, offl = self._sg8_slam_keys(start, r1, cmd, P, N, forced, safe, n_map, M0) \
                if (SG8 and v2 and self._map is not None) else (np.zeros(N), np.zeros(N), np.zeros(N))
            # SG8: the small runes' tier (zeros outside the cast): of the safe rows, in Cast 2 the hop rows first and
            # rows with a dash / air dash last; before it, rows in the air when Cast 2 can start after the others
            hop_m = np.zeros(N, bool)
            if n_hop > n_chase:
                hop_m[N0 + n_spec:N0 + n_spec + n_hop - n_chase] = True
            rtier = self._sg8_rune_keys(f, start, r1, P, N, safe, hop_m) \
                if (SG8 and v2 and self._map is not None and not forced) else np.zeros(N)
            offl = offl + rtier
            # G4 4b (SSBOT_FORUM_SPECIAL_KEEP): the kept template's row, safe and keeping the committed hold and the
            # macro margin, before every other safe row (above the landed hits); no key without the switch
            kk_ = ()
            if n_map:
                # SG4: the map row first among the safe rows (it keeps that priority while the map keeps choosing it:
                # the row is the map's decision rolled out, so it only changes when the map's decision does)
                mk_ = np.zeros(N, bool)
                mk_[M0] = bool(safe[M0] and keep[M0] and mkeep[M0])
                kk_ = (~mk_,)
            if kr is not None:
                kept_ = np.zeros(N, bool)
                kept_[kr] = bool(safe[kr] and keep[kr] and mkeep[kr])
                self.audit.kp_sw_unsafe += int(not kept_[kr])
                kk_ = (~kept_,)
            if hold_on:
                # M4d2: the held bridge (the CONTINUE row) first among the safe rows that keep the commitments; unsafe
                # it ranks as any row (the hold is broken by the planner's own check)
                hm_ = np.zeros(N, bool)
                hm_[N - 1] = bool(safe[N - 1] and keep[N - 1] and mkeep[N - 1])
                kk_ = kk_ + (~hm_,)
                hs_ = self.__dict__.setdefault("hold_stats", {"ticks": 0, "safe": 0})
                hs_["ticks"] += 1
                hs_["safe"] += int(hm_[N - 1])
            gf_ = ()
            gfirst_ = getattr(prefs, "ground_first", None) or ()
            if v2 and gfirst_:
                # SSBOT_FORUM_JB_NOJUMP (task 1v1 SP4; GoalPrefs.ground_first, set only with the switch): behind the
                # landed Clapper, of the safe rows with the same landed hits, one without a jump key first (the SP4
                # replay: at the landing tick a JUMP(48) row with no hit beat CONTINUE on a lower key, and the committed
                # jump kept the next ticks' safe ground slashes out of "keep")
                jr_ = safe & ((cmd & B_JUMP) != 0).any(axis=1)
                self.audit.jb_nojump_ticks += int(jr_.any() and (safe & ~jr_).any())
                gf_ = (jr_.astype(np.int64),)
            nd_ = ()
            if v2 and (getattr(prefs, "no_dash", None) or ()):
                # SSBOT_FORUM_SLAM_PLAY_NODASH (task 1v1 SP4; GoalPrefs.no_dash, set only with the switch): near the
                # idle / walking / evading Clapper the safe rows with a dash key early rank after the ones without,
                # above the landed hits (a dash + run leaves no input when a slam starts: the playbook cannot take it)
                from ssbot.combat import slam_play as _sp
                dr_ = safe & ((cmd[:, :_sp.NODASH_F] & B_DASH) != 0).any(axis=1)
                self.audit.nodash_ticks += int(dr_.any() and (safe & ~dr_).any())
                nd_ = (dr_.astype(np.int64),)
            npg_ = getattr(prefs, "no_pogo", None) or ()
            if v2 and npg_ and len(sc.get("targets") or ()):
                # SSBOT_FORUM_SLAM_PLAY_NOPOGO (task 1v1 SP4; GoalPrefs.no_pogo): a safe row whose first predicted hit is
                # on the idle Clapper from the air (the hero off the ground at the meet frame) after the rest, above
                # the landed hits (the hit starts its attack with her in the air: no landing for the playbook)
                tg_ = sc["targets"]
                ff_ = sc["first_f"]
                on_ = np.array([0 <= int(t) < len(tg_) and tg_[int(t)].iid in npg_ for t in sc["first_t"]], bool)
                fc_ = np.clip(ff_, 0, r1.flags.shape[1] - 1)
                air_ = (r1.flags[np.arange(N), fc_] & F_GROUND) == 0
                pr_ = safe & (ff_ >= 0) & on_ & air_
                self.audit.nopogo_ticks += int(pr_.any() and (safe & ~pr_).any())
                nd_ = nd_ + (pr_.astype(np.int64),)
            rxl_ = None
            rx_ = getattr(prefs, "rune_exit", None) or ()
            if v2 and rx_:
                # SSBOT_FORUM_TWO_RUNEEXIT (task 1v1 SP12a; combat.two_play.rune_exit_late): the safe rows whose end is
                # inside a jump cast's circle still to light with no way out left in time rank after the safe rows
                # that keep one, above the landed hits and NODASH (no key without the switch)
                from ssbot.combat import two_play as _tp
                endb = r1.box[:, -1, :]
                rxl_ = safe & _tp.rune_exit_late(0.5 * (endb[:, 0] + endb[:, 2]), rx_, float(T1 - 1))
                self.audit.rx_ticks += 1
                self.audit.rx_split += int(rxl_.any() and (safe & ~rxl_).any())
                nd_ = nd_ + (rxl_.astype(np.int64),)
            wk_ = ()
            if WIN_RANK and n_ds and win_rows_.any():
                # stage N (SSBOT_FORUM_WINDOWS_RANK): the safe certain window rows first above the landed hits
                wr_ = np.zeros(N, bool)
                wr_[D0:D0 + n_ds] = (ds.cert | (ds.extra > 0)) & win_rows_[D0:D0 + n_ds]
                wr_ &= safe
                if wr_.any():
                    wk_ = ((~wr_).astype(np.int64),)
                    self.audit.win_rank_ticks += 1
            if v2 and rune_bombs.NOGLIDE:
                # SSBOT_FORUM_NOGLIDE (task 1v1 G2): of the safe rows with the same landed hits, one without a glide
                # (the umbrella) first
                gl = safe & (r1.mode[:, P + 1:] == M_GLIDE).any(axis=1)
                self.audit.noglide_ticks += int(gl.any() and (safe & ~gl).any())
                order = np.lexsort((-J, eml_k, -t_hit, -t_c, Pf, Pcm, fs_face, Pc, sk_c, -sk_f, sk_n, fs_bad, ~V,
                                    v2_ff, gl.astype(np.int64)) + gf_ + (v2_nh, offl) + wk_ + nd_ + kk_ +
                                   (~mkeep, ~keep, clash_p, S, U, hz_soft, hz))
            else:
                order = np.lexsort((-J, eml_k, -t_hit, -t_c, Pf, Pcm, fs_face, Pc, sk_c, -sk_f, sk_n, fs_bad, ~V, v2_ff
                                    ) + gf_ + (v2_nh, offl) + wk_ + nd_ + kk_ + (~mkeep, ~keep, clash_p, S, U, hz_soft,
                                                                              hz))
            order = order[sel[order]]
            i = int(order[0])
            tail_ok = None
            carried = cont and i == N - 1 and self.prev_tail_ok
            # the selection's inputs, by reference (offline audits: tools/forum_tv_audit; not logged)
            self.last_sel = {"J": J, "J_tv": sc.get("J_tv"), "eml": eml_k, "nh": sc["nh"], "t_hit": t_hit, "t_c": t_c, "Pc": Pc, "Pcm": Pcm, "Pf": Pf,
                             "sk_n": sk_n, "sk_f": sk_f, "sk_c": sk_c, "clash_p": clash_p, "tk": tk, "V": V,
                             "mkeep": mkeep, "keep": keep, "S": S, "U": U, "hz": hz, "hz_soft": hz_soft, "sel": sel,
                             "allowed": ok & known, "safe": safe, "forced": forced, "first": i, "box": r1.box,
                             "flags": r1.flags, "cmd": cmd, "P": P, "T1": T1, "p_k": fcfg.p_k,
                             **{k: sc.get(k) for k in ("E", "trapped", "overlap", "hexp")},
                             "v2_nh": v2_nh, "ready_pen": dg_pen, "corner": dg_corner, "kk": kk_}
            esc_row = None
            esc_unsafe = False
            if (fcfg.escape or v2) and (not carried or (v2 and forum_v2.ESC_CARRIED)):
                # reactive support: of the safe rows in the order, the first that leaves the hero an escape from
                # every attack an enemy may start at its end or late lock-in (the tail check then looks at it alone);
                # FORCED_RISK: of the first esc_k rows of the order those tied with the first on every key above the
                # share (the share saturates in wave 0 and ties, forum.md §19), the first with an escape
                if not forced:
                    ranked = order[safe[order]]
                else:
                    top = order[:fcfg.esc_k_forced]
                    kk = np.stack([hz, hz_soft, U, S, clash_p, keep, mkeep, V, sk_n, sk_f, sk_c, fs_bad]
                                  ).astype(np.float64)
                    ranked = top[(kk[:, top] == kk[:, [int(order[0])]]).all(axis=0)]
                if not forced or len(ranked) > 1:
                    te = time.perf_counter()
                    hero = (0.0, 0.0) if ws is None or ws.hero is None else \
                        (float(ws.hero.pos.v[0]), float(ws.hero.pos.v[1]))
                    dl = fcfg.esc_deadline_ms if fcfg.esc_deadline_ms is not None else fcfg.deadline_ms + 2.0
                    # review2 (HITS_FIRST): the rows its tiers checked keep their results (the same _escape_fail_v2 on
                    # the same lanes), so the deadline cannot cut them into "unchecked" (the strike flagged unsafe)
                    self._hf_esc = hf_ok_ if (hf_ok_ and v2) else None
                    esc_row, nf, nchk, nth, lab = self._escape_pick(
                        f, start, hold, full, hold_end, r1, ranked, hero,
                        fcfg.esc_k_forced if forced else (fcfg.v2_esc_k if v2 else fcfg.esc_k),
                        None if math.isinf(dl) else t0 + (dl + (map_ms if MAP_DL_SHIFT else 0.0)) * 1e-3, v2=v2)
                    self._hf_esc = None
                    a.esc_cut += int(self.esc_cut)
                    esc_info.update(fail=nf, checked=nchk, threats=nth, forced=bool(forced), cut=self.esc_cut,
                                    ms=round((time.perf_counter() - te) * 1e3, 3), why=sorted(set(lab)))
                    if self.measurement_enabled:
                        esc_info["row"] = esc_row
                    if v2 and forum_v2.ESC_TAIL and esc_row is not None and nf == 0 and esc_row in self._v2_esc_first:
                        esc_tail = (int(esc_row), self._esc_cmds(forum_v2.ESC_F)[self._v2_esc_first[esc_row]])
                    if esc_row is not None:
                        a.esc_ticks += int(not forced)
                        a.esc_pass += int(not forced and nf == 0)
                        a.esc_rows += nchk
                        a.esc_forced_ticks += int(forced)
                        a.esc_forced_pass += int(forced and nf == 0)
                        a.esc_forced_moved += int(forced and esc_row != i)
                        i = esc_row
                    if (fcfg.esc_veto or v2) and not forced:
                        # "+n": the attacks not started are the escape check's only; a row it failed (the fewest
                        # failures of those checked) or did not reach before its deadline with threats in reach is not
                        # safe (forum.md §23.12)
                        failed = esc_row is not None and nf > 0
                        unchecked = esc_row is None and nchk == 0 and (nth > 0 or fcfg.light_cone) and len(ranked) > 0
                        esc_unsafe = failed or unchecked
                        a.esc_failed += int(failed)
                        a.esc_unchecked += int(unchecked)
                        esc_info["unsafe"] = esc_unsafe
            elif carried and (fcfg.esc_veto or v2) and self.prev_esc_unsafe:
                esc_unsafe = True                  # the CONTINUE of a row the escape check did not pass
                a.esc_carried += 1
            if not forced and cfg.tail_k > 0 and not carried:
                ranked = order[safe[order]] if esc_row is None else np.array([esc_row], np.int64)
                i, tail_ok = self._tail_pick(f, r1, hold_end, ranked, P + T, i)
            elif carried:
                tail_ok = True
            self.last_sel["chosen"] = i
            if kr is not None and len(kk_) and not kk_[0][kr]:
                self.audit.kp_kept += int(i == kr)
                self.audit.kp_sw_escape += int(i != kr)
            self.prev_tail_ok = bool(tail_ok)
            self.prev_esc_unsafe = bool(esc_unsafe and not S[i])
            a.esc_unsafe += int(esc_unsafe and not S[i])
            sel_cmd = cmd[i]
            name = rname(i)
            a.spec_chosen += int(N0 <= i < N0 + n_spec)
            a.hop_chosen += int(N0 + n_spec <= i < N0 + n_spec + n_hop - n_chase)
            a.chase_chosen += int(n_chase > 0 and N0 + n_spec + n_hop - n_chase <= i < N0 + n_spec + n_hop)
            if dslash.DSLASH:
                self._ds_prev = None
                if D0 <= i < D0 + n_ds and not S[i]:
                    q_ = i - D0
                    a.ds_chosen += 1
                    a.ds_chosen_cert += int(ds.cert[q_])
                    a.ds_chosen_chain += int(ds.c2[q_] >= 0)
                    self._ds_prev = np.asarray(ds.ext[q_], np.int64)
            if win_ is not None:
                # task oldwin: the chosen window row (safe) continues next tick while she follows it (WindowRows.cont)
                wc_ = getattr(self, "_win_c", None)
                q_ = i - D0 - getattr(self, "_win_off", 0)
                ch_ = wc_[q_] if (wc_ is not None and n_ds and D0 <= i < D0 + n_ds and 0 <= q_ < len(wc_)
                                  and not S[i]) else None
                win_.note_chosen(ch_, int(ws.stamp.frame) + P - 1, int(ws.stamp.frame),
                                 r1.phys[i] if ch_ is not None else None, r1.vel[i] if ch_ is not None else None)
                if ch_ is not None:
                    a.win_chosen += 1
                    self._ds_prev = None          # (DSLASH on: no 'DS cont' of a window row - its own continuation)
                if self._win_info is not None:
                    self._win_info["chosen"] = None if ch_ is None else [ch_.kind, ch_.wt, ch_.label, ch_.key,
                                                                         int(cmd[i][0])]
                    if wc_:
                        ps_ = Counter()
                        for m_, c_ in enumerate(wc_):
                            r_ = D0 + getattr(self, "_win_off", 0) + m_
                            if r_ < len(safe) and safe[r_]:
                                ps_[c_.wt] += 1
                        self._win_info["pass"] = dict(ps_)
                    self._win_info["S"] = int(S[i])
            if sctx is not None and i in set(sctx.rows.tolist()):
                q_ = int(np.searchsorted(sctx.rows, i))
                if sctx.appr_fail[q_] < 0:
                    sctx.appr_fail[q_] = special_mode.real_approach_fail(sctx.tl, sctx.k0, sctx.xa, sctx.cy, sctx.face,
                                                                         int(sctx.pj[q_]), sctx.box[q_], sctx.flags[q_])
                a.sm_chosen += int(not S[i])
                a.sm_appr_fail += int(not S[i] and bool(sctx.appr_fail[q_]))
                a.sm_appr_hammer += int(not S[i] and int(sctx.appr_fail[q_]) == 2)
                if not S[i] and not esc_unsafe:
                    self._prev_sm = {"iid": sctx.iid, "ext": sctx.ext[q_].copy(), "move": sctx.move}
                    if (getattr(self, "_spec_meta", None) or {}).get("by_map"):
                        self._prev_sm["map"] = True     # SG4: its CONTINUE keeps the full checks (review)
            res = PlanResult(int(sel_cmd[0]), i, name, int(S[i] or esc_unsafe), forced, float(Pc[i]), float(J[i]),
                             bool(V[i]),
                             bool(hz[i]), bool(U[i]), N, int(ok.sum()), int(safe.sum()), sel_cmd, r1.box[i].copy(),
                             bound[i].copy(), hits=float(sc["hits"][i]))
            res.tail_ok = tail_ok
            res.clash = (float(clash_w[i]), int(clash_n[i]), i in clash_occ) if clash_n[i] else None
            a.clash_chosen += int(clash_n[i] > 0 and i not in clash_occ)
            a.clash_partial_chosen += int(i in clash_occ)
            if may_kill[i] or in_flight[i]:
                res.kill = KillPlan(own=bool(may_kill[i]), certified=False, i3=i3_kill_allowed(ctx),
                                    k_lo=int(k_lo[i]), k_hi=int(k_hi[i]),
                                    window=kill_window_frames(params.frame_time, ctx.kill_window_s), P=P)
            for j_ in order[1:6]:
                nm = rname(int(j_))
                res.alternatives.append((nm, int(S[j_]), round(float(Pc[j_]), 3), round(float(J[j_]), 2)))
            if not S[i]:
                a.chosen_safe += 1
                a.chosen_safe_enveloped += int(env[i])
            else:
                a.forced += int(forced)
                a.forced_enveloped += int(forced and env[i])
                a.forced_stage1 += int(forced and not env[i])
        else:
            sel_cmd = np.zeros(T, np.int64)
            res = PlanResult(0, -1, "NONE", 1, True, n=N)
            a.forced += 1
        res.vetoes = {REASONS_FORUM[k]: int(v) for k, v in zip(*np.unique(why, return_counts=True)) if k}
        res.idle_clear = idle_clear
        if len(sel_cmd) and sel_cmd[0] & B_JUMP:
            if self.jump_until <= self.ticks:
                held = sel_cmd & B_JUMP
                self.jump_until = self.ticks + (int(np.argmin(held != 0)) if (held == 0).any() else len(held))
        else:
            self.jump_until = -1
        if _is_macro(res.name):
            last = np.flatnonzero((sel_cmd & kin.B_DOWN) != 0)
            self.macro_until = self.ticks + (int(last[-1]) + 12 if len(last) else 0)
        elif res.name != "CONTINUE":
            self.macro_until = -1
        self.prev_cmd = sel_cmd
        if sctx is not None:
            # (e) the decision for the L2 controller (special_mode.BOARD): on = a special row safe after every check;
            # x = the hero's x at the press of the chosen one, else of the best safe one
            sq = np.flatnonzero(safe[sctx.rows])
            on = bool(len(sq))
            bx_ = None
            if on:
                ch_ = [int(np.searchsorted(sctx.rows, res.idx))] if res.idx in set(sctx.rows.tolist()) else \
                    [int(sq[np.argmax(J[sctx.rows[sq]])])]
                q_ = ch_[0]
                bx_ = float(sctx.pos[q_, min(int(sctx.pj[q_]), sctx.pos.shape[1] - 1), 0])
            special_mode.BOARD[sctx.iid] = {"tick": self.ticks, "move": sctx.move, "k": sctx.k0, "on": on, "x": bx_,
                                            "rows": len(sctx.rows), "safe": len(sq)}
            if special_mode.FAST:
                self._sm_board(sctx.iid, sctx.move, sctx.k0, on, bx_)
        if special_mode.FAST and sm_on and sctx is None and getattr(self, "_spec_meta", None) is not None:
            m_ = self._spec_meta
            self._sm_board(m_["iid"], m_["move"], m_["k0"], False, None)
        if getattr(self, "_prev_sm", None) is not None and res.idx >= 0 and not S[res.idx]:
            # the chosen special row's plan is its whole template (the next CONTINUE runs on into the press and
            # the bounce, judged as a special row again)
            self.prev_cmd = np.asarray(self._prev_sm["ext"], np.int64)
        if esc_tail is not None and esc_tail[0] == res.idx and getattr(self, "_prev_sm", None) is None:
            # v2: the escape that kept this row safe is its plan's tail: the next tick's CONTINUE runs into it
            # (forum_v2.ESC_TAIL) instead of idling where the row ends
            self.prev_cmd = np.concatenate([np.asarray(sel_cmd, np.int64), esc_tail[1]])
            a.v2_esc_tail += 1
        if special_mode.KEEP:
            # G4 4b: what is kept next tick: a chosen special row (its CONTINUE), else a chosen family row
            self._kp = "sm" if getattr(self, "_prev_sm", None) is not None else                 ("ds" if (n_ds and D0 <= res.idx < D0 + n_ds and not S[res.idx]) else None)
            if self._kp == "ds":
                # a chain's second press offset after the first bounce (its name's "+c<b>"), while its first strike
                # is still ahead (two presses in its plan); else none
                nm_ = ds.names[res.idx - D0]
                ext_ = np.asarray(ds.ext[res.idx - D0])
                a_on = (ext_ & B_ATTACK) != 0
                n_pr = int((a_on & ~np.concatenate([[False], a_on[:-1]])).sum())
                self._ds_keep_b = int(nm_.rsplit("+c", 1)[1]) if ("+c" in nm_ and n_pr >= 2) else None
            else:
                self._ds_keep_b = None
        map_info = None
        if SPECIAL_MAP and self._map is not None:
            # SG4: the map row's outcome this tick (the overlay and the decision log read it), L2's spot
            taken = bool(n_map and res.idx == M0 and not S[M0])
            if n_map:
                a.map_ticks += 1
                a.map_safe += int(not S[M0])
                a.map_taken += int(taken)
                a.map_xcheck += int(bool(map_x))
                self._map.chosen(taken, mrow.plan)
            elif self._map.info is not None:
                a.map_off += 1
                self._map.off_board(f, start, self.ticks)
            mi_ = self._map.info
            ri_ = self._map.ready_info
            if mi_ is not None or ri_ is not None:
                first_ = (self.last_sel or {}).get("first")
                ls_ = self.last_sel or {}

                def at_(nm):
                    a_ = ls_.get(nm)
                    return None if a_ is None or not hasattr(a_, "__len__") else bool(a_[M0])
                map_info = {**(mi_ or {}), **({"row": int(M0), "safe": bool(not S[M0]), "xcheck": map_x,
                                               "chosen": res.name, "lane": [mrow.meta.get("lane_dx"),
                                                                            mrow.meta.get("lane_dy")],
                                               "s1": bool(S1[M0]), "env": bool(env[M0]), "ok": bool(ok[M0]),
                                               "first": bool(first_ == M0), "keep": at_("keep"),
                                               "mkeep": at_("mkeep"), "hz": at_("hz"), "U": at_("U")}
                                              if n_map else {}),
                            **({"ready": ri_} if ri_ is not None else {})}
            self._map.ready_info = None
        self.prev_name = res.name
        self.ticks += 1
        self.last_map_ms = map_ms                 # SG6: the map's own work this tick (diagnostics)
        t6 = time.perf_counter()
        self.last_info = {"dash_only": getattr(self, "v2_dash_only", None), "posture": posture, "N": N, "stage1_pass": int(pass1.sum()), "enveloped": int(env.sum()),
                          "core": int(core.sum()), "core_pass": n_core, "prio": n_prio, "overrun": overrun,
                          "cut": cut, "hitfx": budget["hitfx"], "react": budget["react"], "capped": budget["capped"],
                          "uncapped": budget.get("uncapped", 0),
                          "S": S, "Hz": hz, "U": U, "core_mask": core, "env": env, "Pc": Pc, "Pcm": Pcm, "Pf": Pf,
                          "t_c": t_c,
                          "cand": sel if forced else np.zeros(N, bool), "hit_occ": hit_occ,
                          "seen": int(sk_n[res.idx]) if res.idx >= 0 else None,
                          "seen_cf": round(float(sk_c[res.idx]), 3) if res.idx >= 0 else None,
                          "esc": esc_info or None}
        if rxl_ is not None:
            # SP12a: [safe rows late for a circle's exit, safe rows, the chosen row late]
            self.last_info["rx"] = [int(rxl_.sum()), int(safe.sum()),
                                    bool(0 <= res.idx < len(rxl_) and rxl_[res.idx])]
        if map_info is not None:
            self.last_info["map"] = map_info
        if getattr(self, "win", None) is not None and getattr(self, "_win_info", None) is not None:
            self.last_info["win"] = self._win_info           # task oldwin
        if self.debug:
            self.last_info["dbg"] = {"box": r1.box, "flags": r1.flags, "mode": r1.mode, "latched": latched, "P": P,
                                     "J": J, "ok": ok, "known": known, "t_hit": t_hit, "V": V, "keep": keep,
                                     "names": [rname(i) for i in range(N)],
                                     "chosen": int(res.idx), "fr": fr, "o": o, "tk": tk}
        if "E" in sc:
            ci = res.idx if 0 <= res.idx < N else None
            self.last_info["tv"] = {"ms": round(sc["tv_ms"], 3), "field_ms": round(sc["field_ms"], 3),
                                    "kv": {str(k): round(v, 3) for k, v in sc["kv"].items() if v > 0},
                                    **({} if ci is None else {"E": round(float(sc["E"][ci]), 3),
                                                              "trapped": bool(sc["trapped"][ci]),
                                                              "overlap": round(float(sc["overlap"][ci]), 3),
                                                              "hexp": round(float(sc["hexp"][ci]), 3)}),
                                    "E_max": round(float(sc["E"].max()), 3),
                                    "trapped_share": round(float(sc["trapped"].mean()), 3)}
        res.t_ms = {"filter": (t1 - t0) * 1e3, "rollout": (t2 - t1) * 1e3, "score": (t3 - t2) * 1e3,
                    "envelope": (t4 - t3) * 1e3, "prob_bind": (t5 - t4) * 1e3, "select": (t6 - t5) * 1e3,
                    "total": (t6 - t0) * 1e3, "s1_rollout": (t1r - t1) * 1e3, "s1_support": (t2 - t1r) * 1e3}
        if self.measurement_enabled:
            self.measurement_result = res
        return res
