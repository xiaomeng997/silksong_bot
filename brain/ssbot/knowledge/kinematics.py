"""Hero kinematics for the planner (M2 W1; DESIGN §3.5.2, §3.5.4, §3.5.6): a hybrid-mode model of Hornet's motion,
re-derived from the decompiled HeroController (1.0.30000) and identified on logged play, a batched rollout with 2D
collision against the scene's static terrain (compiled: ssbot.knowledge.kin_jit), timing-variant lanes for the
+-1 frame branches, the input filter, a per-frame state tracker and a runtime residual monitor. The damage-knockback
envelope is in ssbot.knowledge.knockback.

    params = HeroParams.load()                                  # knowledge/1.0.30000/kinematics/hero_hunter.json
    terrain = Terrain2D.from_message(terrain_msg, params.scene("Bone_05"))   # RecordingReader.terrain() payload
    trk = StateTracker(params, terrain); trk.push(state)        # every STATE: O(1), under 0.1 ms
    start = trk.state()                                         # [K, 1]: estimate_state(Trace.from_states(history),
                                                                #   [last row], params, terrain=terrain), bit for bit
    hold = HoldState.from_act(state["act"])                     # or the planner's own, kept in step with its ACTIONs
    latched, hold_next = hold_filter(commanded, hold)           # commanded masks [N, T] -> what the game will read
    roll = rollout(start, latched, params, terrain, threads=4)  # roll.box [N, T+1, 4] collider boxes, roll.centre
    roll = rollout(start, latched, params, terrain, variants="bounds", threads=4)   # roll.bound / flags_all: the
                                                                #   timing lanes' per-frame hull (the support form)
    hull, flags = knockback.knockback_hull(roll.box, params, terrain, udt_history=udts)   # Hz(c), KF_UNKNOWN
    mon = ResidualMonitor(params, terrain); mon.update(trk); mon.confidence()   # I4 "kinematics"; None: unknown

Positions follow cross-module decision 1: Rollout.box is the hero collider (STATE hero.box), Rollout.centre its
centre (WorldState HeroState.pos); Rollout.pos is the rendered transform (pos_transform).

Acceptance (ssbot.tools.kin_check, every 30-frame window, collider centre within 0.1 u after 0.5 s; decision 3:
start state from the history up to the window start only, causal phase, nominal timing; parameters fitted on live
20261001_122249 i0_000, the Bind lengths on i0_000 + i0-3_002; 2026-10-01 after the world-freeze model). Held out:
the trial run 20261001_121446 i0_000 and live i1-3_000, i0-3_001 (8 recordings, 1 915 915 windows, 38 640
uncovered and counted as misses in "all": control taken by another FSM 25 667, invalid 6 950, harness 6 015,
savestate slide 8):
  nominal lane, logged contact and freeze events standing in for the threat layer: 89.8 % of covered windows
    (89.1 % of all); plain primitives 99.6 % (run 99.5, jump 99.4, air 99.6, attack 99.1, idle 99.99), cast 93.0,
    bind 96.6, contact (nail recoil, pogo, recoil down, early catch) 80.5, downspike 77.0, hurt 66.3, recovering
    (starting in the hit-stop or recoil) 55.7, world_freeze (BindBreak, BossDeathSlow, boss stun) 70.7 (60.3 before
    the world-freeze model), hitch 80.6;
  the same without events (the buttons alone): 80.1 %;
  inside the hull of the 9 "bounds" timing lanes dilated by 0.1 u (hull spread p50 0, p95 0.39, p99 0.65 u):
    99.22 % of covered windows (98.32 % of all; plain 99.89, hurt 99.65, recovering 98.7, downspike 98.0, contact
    97.6, cast 97.0, bind 98.1, world_freeze 73.7, hitch 87.3);
  replay with the logged dt / physics steps (information the planner does not have): 99.42 %.
The fit recording gives the same (89.7 / 99.25 %), and so do the later live recordings i0-3_002 (89.6 / 99.22 %).
So the DESIGN §3.5.2 target (99 % within 0.1 u) is met by the nominal point prediction for plain movement only, and
in the planner's information set no point prediction can meet it overall: most nominal misses are one physics step,
3 615 of the 4 630 missed hurt windows of live i1_000 f < 120 000 are 0.32-0.36 u off (one recoil step, 0.335 u),
644 two steps; hit-stop (13 / 14 / 15 frames) and recoil (13 / 14) end on frames that frame times of 0.01665 against
1/60 s decide, which the history does not predict (with the future frame times, the replay: 99.4 %). What the model
delivers at 99 % is the support form, the lanes' hull (Rollout.bound), which the planner checks and the residual
monitor watches; restating the M2 exit item that way (hull containment, with the hull spread in the hazard margin)
is the lead's decision. A person's session (20260930_210337, "input" masks, 113 369 covered windows) reaches 90.0 %
nominal, 91.0 % in the lanes' hull: plain movement 92.6 %, as the "input" stream is not the exact latched mask.

Planner cost (13900K, Bone_05 terrain, 512 candidates x 48 frames, measured with other work on the machine): the
nominal rollout p50 2.3 ms / p99 3.0 ms on one core, p50 0.47 / p99 0.8 ms with threads=4; the "bounds" lanes in the
planner's form (lanes=False: no per-lane arrays, and a candidate that meets no hit-stop or world freeze runs 3 of the
9, the others being identical for it) p50 1.4-1.5 ms / p99 1.9-2.2 ms with threads=4 (6.8 ms on one core), the
"fast" lanes the same; knockback_hull p99 0.15 ms; the start state from StateTracker under 0.1 ms per frame
(push_row 0.06 ms; rebuilding it from a 240-frame STATE tail costs 2.5 ms). So every candidate can carry its lanes'
hull within the 3 ms budget, the knockback hull included.

Time base (trial run, 26 892 STATE frames; ssbot.tools.kin_fit):
- Physics steps at fdt = 0.02 s of scaled time under the render (mean frame 0.0166662 s, p1 0.01665, p99 0.01671).
  STATE "fs" counts the FixedUpdate calls in a frame: 0 or 1 at 60 fps (5 570 / 21 322 frames), 2 only after a
  hitch; "dt" is the scaled Time.deltaTime (0 in hit-stop), "udt" the unscaled one, "ts" the time scale.
- Unity runs a frame's FixedUpdates before its input update and Update, so an ACTION latched for frame F (STATE
  "act".mask; oracle/src/Input/ActionScheduler.cs applies it at the first input update with frame >= F) is read by
  HeroController.Update in F and reaches the body at the first physics step of a later frame. The "input" exporter
  shows a jump press one frame late and its release on time (human session 20260930_210337: 652 of 672 jumps after
  the shift; bot runs: act vs input), so traces built from "input" move the press back (HeroParams.input_jump_lag).
- The hero's Rigidbody2D interpolates: STATE hero.pos is the rendered transform, lerp(Q, S, alpha) between the poses
  before and after the last step with alpha = (Time.time - Time.fixedTime) / fdt, while hero.box (collider bounds)
  follows the body itself. Running at 8.25 u/s moves pos 0.1375 u every frame and the box 0.165 u per step. The model
  integrates the body per step and renders pos the same way; a position set in Update (BecomeAirborne lifts the body
  0.02 u) shows in the box at once and in pos only after the next step.
- Integration is semi-implicit (v += g gs dt; p += v dt) with g = 60 u/s^2 (1.2 u/s per step at gravityScale 1).
- Game timers are float32 sums of float32 frame times; the model sums the same way, so the threshold crossings that
  flip with the frame time (antic 6 or 7 frames, hit-stop 13 / 14 / 15 frames, damage recoil 13 / 14) land on the
  logged frame when the logged dt / udt are replayed.

Modes and what drives them (all from HeroController.FixedUpdate / Update unless noted):
  NORMAL      control on the ground or in the air: run (vx = move * 8.25, no acceleration), jump (vy = 18.6 for
              steps 0..8; full hold peaks 5.50 u up), release (vy *= 0.5 every Update while vy > 0 and
              jumped_steps >= 2), air hang (gravity scale 0.1 at the first falling step, +0.1 per step while jump
              is held, back to 1 when it is not), max fall 30, input queues (jump 2 / attack 8 steps), attacks (no
              motion of their own), landing recovery after a downspike (no running for 0.167 s).
  DS_ANTIC    Hunter down attack (DownSpike type): relinquished, gravity off, vy clamped to >= -12, v *= 0.8 per
              step while the 0.1 s antic timer runs.
  DS_SPIKE    (+-26, -26) along the facing while the 0.1 s FixedUpdate timer runs, then vy = -10, control back;
              touching the floor ends it at once.
  HURT_FREEZE damage hit-stop (GameManager.FreezeMoment 0 / 0.1 / 0.1): v = 0, gravity off; the wait sums udt from
              the second frame after the hit, then the time scale ramps back to 1 over 0.1 s of udt (replayed
              exactly with the logged udt: 987 of 987 hits of live i0_000).
  HURT_RECOIL v = (+-15, 7.5) away from the impact side until recoilTimer reaches RECOIL_DURATION 0.2 s, then v = 0,
              gravity back, control back (before LookForQueueInput, so a queued attack starts in that frame).
  CAST        Silkspear (Spell FSM, quickcast, 4 silk): antic 0.26 s (air v *= 0.9 per step, rising vy capped at
              12; ground vx *= 0.85), throw (still) until the needle is back, catch (v = (-21 facing, 0), vx *= 0.7
              per step, gravity on). Throw and catch end on one of two frames with no timer explaining which (live
              i0_000: throw 26 / 27 frames 46 / 54 %, catch 9 / 10 frames 41 / 59 %): variant-valued thresholds
              (HeroParams.cast_throw_variants / cast_catch_variants, the variant lanes take both).
  BIND        Bind (9 silk): 1.34, 1.36 or 1.37 s (81 / 82 / 83 frames, bind_time_variants: 28 / 56 / 17 % of
              18 binds of live i0_000 and i0-3_002; the 37 binds of the 8 held-out recordings fall in the same three
              intervals); air v *= 0.85 per step (rising vy capped at 7.5), gravity off. A hit in the first 1.2 s
              (the charge, before BindBurst) also starts the BindBreak world freeze.
  LOCKED      control taken by another FSM (the boss roar): vx *= 0.86 per step, gravity on.
World freezes (rows WF_*): GameManager.FreezeMoment coroutines other than the hero's own hit-stop, each a time-scale
control that TimeManager multiplies into Time.timeScale: ramp down to the target over rampDown, wait, ramp back up,
on float32 sums of unscaled time (presets FREEZE_PRESETS, GameManager.cs 5092-5141: BindBreak 0.01 / 0.4 / 0.1 to 0,
BossDeathSlow 0.1 / 1.15 / 0.1 to 0.05, BossStun 0 / 0.25 / 0.1, QuickFreeze, EnemyDeath). The model's time scale is
TS (the hero's hit-stop) times WF_S. BindBreak follows from the hero's own state: a hit during the Bind charge (22 of
22 logged, 0 of 1 in the burst) keeps the scale at 0 for 0.4 s, so the recoil waits about 12 frames after the
hit-stop (live i1_000 f 153335: nominal error 0.34 u, 3.7 u without it). The others come with the boss (killing
blow, stun, a small enemy's death): EV_FZ_* events, which the threat layer announces as it does contacts. The
estimator replays a running freeze from its logged start.
Contact events do not follow from the buttons; a rollout takes them as an optional per-frame array (the threat layer
predicts them; ssbot.tools.kin_check injects the logged ones): EV_RECOIL_L/R (a nail hit: vx = -+3.75 now and for
8 more steps), EV_POGO (a down attack hit: jump steps from 4, jumped_steps -20), EV_HURT_L/R (impact from that
side), EV_RECOIL_DOWN (an up slash hit: the rise stops), EV_CATCH (the Silkspear needle came back early), EV_SILK
(+1 silk from a hit: Bind and Silkspear need it), EV_LOCK / EV_UNLOCK, EV_FZ_BOSS_DEATH / BOSS_STUN / QUICK /
ENEMY_DEATH (a world freeze starts).

Collision moves the hero box (0.5 x 2.079, foot 1.5527 below hero.pos) along x then y against axis-aligned terrain
segments with a 0.015 u skin (standing box bottom 2.0150 over the Bone_05 floor at 2.0; arena gate faces 69.208 /
102.002 against hero x 69.473 / 101.737). Box2D details that move positions by more than a few mm are kept: a fall
that ends within [-0.0082, +0.0053] u of the resting height parks there and makes contact a step later (122 of 2 865
landings of live i0_000), contacts are found before the move (walking off a ledge sinks from the next step), a spike
that touches the floor ends there. Sloped edges are not collided by the rollout: Bone_05 has them only in the roof
(y >= 13.9 inside the arena), out of reach of a jump from the floor but not of a pogo off the boss or a knockback
(live i2_002 f 693717); the knockback bound handles them, a rollout up there is off (the residual monitor sees it).

Timing lanes (Variant): the frame time is not predictable from the history, so a +-1 frame branch cannot be
resolved, only carried. The lanes move every float32 timer threshold by -+ timer_bias (0.5 ms: each link of the
unscaled wait / ramp chain, hit-stop and world freeze alike, and the scaled timers, with its own sign), start the
physics phase at either end of its feasible interval (+- alpha_margin) and take the short or long Silkspear and Bind
variants; Rollout.bound is their per-frame hull, flags_all / flags_any their flags. The frame-time jitter model
(kin_fit over 2.83 M gameplay frames of all bot recordings: frame_time mean 0.016666 s, shortest 0.01665, p99.99
0.01698, at most 2 frames above 0.018 s in any 65, longest 0.0369 s, rate 3.1e-5 per frame above 0.018 s) sets the
lanes' frame times and the knockback bound (knockback.TimingGuard checks it at run time). ResidualMonitor (DESIGN
§3.5.2, I4 "kinematics") re-rolls the executed masks and observed events from anchor states and checks the observed
box against the lanes' hull at 1 / 6 / 30 frames; frames the model does not own (StateTracker.modelled: harness,
scene, locked, nail arts, unexplained freezes, hitches) drop their windows. HeroParams.jump_heights holds the apex
height per jump hold length, logged (min, median, max) against the model over the phase and frame time: the hold ->
height spread for the hazard margin (0.05-0.35 u, the 50 Hz steps falling differently among the frames; the model
range holds every logged apex of live i0_000 within 4 mm).

Implementation: the model state is one float64 array [K, N] (rows below) and the parameters one float64 vector. The
NumPy functions here (_fixed_step, _apply_events, _update, _simulate) are the readable reference, array code over
lanes; kin_jit is the same rules per lane as numba-compiled scalar code, which rollout() uses (backend "auto"), and
the tests check both give identical arrays.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Iterable

import numpy as np

try:  # pragma: no cover - numba 0.68 is installed; the NumPy reference works without it
    import numba  # noqa: F401
    HAVE_NUMBA = True
except ImportError:
    HAVE_NUMBA = False

REPO = Path(__file__).resolve().parents[3]
FDT = 0.0199999921     # Time.fixedDeltaTime (hero_constants.json engine)
DEFAULT_PARAMS = REPO / "knowledge" / "1.0.30000" / "kinematics" / "hero_hunter.json"

# ---- model state rows -----------------------------------------------------------------------------------------
(PX, PY,          # body position in hero.pos coordinates (x centre, y = box bottom + foot)
 QX, QY,          # body position at the start of the last step (render interpolation from)
 SX, SY,          # body position at the end of the last step (render interpolation to)
 VX, VY,
 ALPHA,           # (Time.time - Time.fixedTime) / fdt
 GS,              # gravity scale
 FACE,            # +1 right, -1 left
 GROUND,
 MODE, MODE_T,    # mode and scaled seconds in it (or steps, for DS_SPIKE)
 MODE_N,          # frames in mode (hit-stop is counted in frames)
 JUMPING, JSTEPS, JDSTEPS,
 JQ, AQ,          # jump / attack queue steps (-1: not queuing)
 AIRHANG,         # didAirHang
 ATTACKING, ATK_T, ATK_CD,
 RDIR, RSTEPS,    # nail recoil direction (-1 left, +1 right, 0 none) and recoilStepsLeft
 DS_HS,           # downspike horizontal speed
 DS_REC,          # downspike recovery timer (-1: not recovering)
 BOUNCE,          # downspike rebound steps (-1: not bouncing)
 HVX, HVY,        # damage recoil vector
 MOVE, JHELD,     # move_input and Jump.IsPressed as of the last Update
 PREV,            # button mask of the previous frame (edges)
 SILK,
 INV_T,           # i-frame seconds left (scaled)
 LEDGE,           # ledge buffer steps
 TOUCH,           # the last step ended in floor contact without penetration: Box2D resolves it a step later
 PHASE,           # sub-phase: hit-stop 0 wait / 1 ramp; Silkspear 0 antic / 1 throw / 2 catch
 TS,              # time scale the next frame runs at (nominal timing; logged runs take dt from the log)
 QQ,              # quickcast (tool / Silkspear) queue steps (-1: not queuing)
 ALO, AHI,        # feasible interval of ALPHA (the timing-variant lanes start from its ends)
 LANDQ,           # landed in this frame's physics steps: its Update decides idle (recovery ends) or run (it stays)
 WF_PH, WF_T,     # world freeze (GameManager.FreezeMoment other than the hero's hit-stop): phase -1 none, 0 ramp down,
                  # 1 wait, 2 ramp up (+10: started in this frame, the coroutine's first step done), timer (unscaled)
 WF_S,            # its time-scale factor (the effective scale is TS * WF_S: TimeManager multiplies the controls)
 WF_DOWN, WF_WAIT, WF_UP, WF_TGT,   # its preset (FREEZE_PRESETS)
 K) = range(52)
ROW_NAMES = ("px py qx qy sx sy vx vy alpha gs face ground mode mode_t mode_n jumping jsteps jdsteps jq aq airhang "
             "attacking atk_t atk_cd rdir rsteps ds_hs ds_rec bounce hvx hvy move jheld prev silk inv_t ledge touch "
             "phase ts qq alo ahi landq wf_ph wf_t wf_s wf_down wf_wait wf_up wf_tgt").split()
assert len(ROW_NAMES) == K

M_NORMAL, M_DS_ANTIC, M_DS_SPIKE, M_HURT_FREEZE, M_HURT_RECOIL, M_CAST, M_BIND, M_LOCKED = range(8)
MODE_NAMES = ("NORMAL", "DS_ANTIC", "DS_SPIKE", "HURT_FREEZE", "HURT_RECOIL", "CAST", "BIND", "LOCKED")
RELINQUISHED = (M_DS_ANTIC, M_DS_SPIKE, M_CAST, M_BIND, M_LOCKED)    # controlReqlinquished
NO_INPUT = (M_HURT_FREEZE, M_HURT_RECOIL)                             # hero_state no_input

# contact events (bit flags per frame; applied after the frame's physics steps, before its Update)
EV_RECOIL_L, EV_RECOIL_R, EV_POGO, EV_HURT_L, EV_HURT_R, EV_LOCK, EV_UNLOCK, EV_CATCH, EV_SILK, EV_RECOIL_DOWN, \
    EV_FZ_BOSS_DEATH, EV_FZ_BOSS_STUN, EV_FZ_QUICK, EV_FZ_ENEMY_DEATH, EV_FZ_BIND_BREAK = (1 << i for i in range(15))
# world freezes a rollout can be told about (the threat layer predicts them: a killing blow, a stun, a small enemy's
# death; BindBreak also starts by itself on a hit during the Bind charge): GameManager.FreezeMoment presets
# (rampDown, wait, rampUp, target speed; GameManager.cs 5092-5141)
FREEZE_PRESETS = {EV_FZ_BOSS_DEATH: (0.1, 1.15, 0.1, 0.05), EV_FZ_BOSS_STUN: (0.0, 0.25, 0.1, 0.0),
                  EV_FZ_QUICK: (0.0001, 0.02, 0.0001, 0.0001), EV_FZ_ENEMY_DEATH: (0.04, 0.024, 0.04, 0.0),
                  EV_FZ_BIND_BREAK: (0.01, 0.4, 0.1, 0.0)}
# start order within a frame, shortest first: when two start together the model keeps the longer one (in the game
# both run and their scales multiply; logged only for EnemyDeath with every hit, which ends inside the hit-stop)
WF_ORDER = (EV_FZ_QUICK, EV_FZ_ENEMY_DEATH, EV_FZ_BOSS_STUN, EV_FZ_BIND_BREAK, EV_FZ_BOSS_DEATH)
EV_FZ_ANY = EV_FZ_BOSS_DEATH | EV_FZ_BOSS_STUN | EV_FZ_QUICK | EV_FZ_ENEMY_DEATH | EV_FZ_BIND_BREAK
EVENT_NAMES = {EV_RECOIL_L: "recoil_l", EV_RECOIL_R: "recoil_r", EV_POGO: "pogo", EV_HURT_L: "hurt_l",
               EV_HURT_R: "hurt_r", EV_LOCK: "lock", EV_UNLOCK: "unlock", EV_CATCH: "catch", EV_SILK: "silk",
               EV_RECOIL_DOWN: "recoil_down", EV_FZ_BOSS_DEATH: "freeze_boss_death",
               EV_FZ_BOSS_STUN: "freeze_boss_stun", EV_FZ_QUICK: "freeze_quick",
               EV_FZ_ENEMY_DEATH: "freeze_enemy_death", EV_FZ_BIND_BREAK: "freeze_bind_break"}

# rollout flags
F_GROUND, F_JUMPING, F_ATTACKING, F_RECOIL, F_RELINQ, F_INVULN, F_NO_INPUT = (1 << i for i in range(7))

# ACTION button bits (ssbot.ipc.framing.BUTTONS order)
B_JUMP, B_ATTACK, B_BIND, B_QUICKCAST = 1 << 0, 1 << 1, 1 << 3, 1 << 6
B_UP, B_DOWN, B_LEFT, B_RIGHT = 1 << 18, 1 << 19, 1 << 20, 1 << 21

EPS = 1e-4       # open-interval margin for overlap tests
TOL = 0.05       # a box this far inside a face still counts as in front of it (Box2D leaves ~2 mm at seams)
GTOL = 8e-3      # ground probe (covers the touch band of _move_y)
TT_HEAD = 14     # header length of Terrain2D.packed() (layout in kin_jit)
ROUND_MIN = 0.02  # edge radius below which a shape counts as sharp (Box2D's own polygon skin is 0.01)


# ---- parameters -----------------------------------------------------------------------------------------------

@dataclass(slots=True)
class HeroParams:
    """Model constants. Values start from hero_constants.json / crests.json (HeroController prefab and the Hunter
    crest config) and are confirmed or replaced by ssbot.tools.kin_fit; `source` says which, per key."""
    build: str = "1.0.30000"
    crest: str = "Hunter"
    fdt: float = FDT
    frame_time: float = 1 / 60
    gravity: float = 60.0
    run_speed: float = 8.25
    jump_speed: float = 18.6
    jump_steps: int = 8
    jump_steps_min: int = 2
    jump_queue_steps: int = 2
    attack_queue_steps: int = 8
    tool_queue_steps: int = 5
    jump_release_mult: float = 0.5
    air_hang_gravity: float = 0.1
    air_hang_accel: float = 5.0
    max_fall: float = 30.0
    airborne_lift: float = 0.02
    half_width: float = 0.25
    foot: float = 1.5527
    head: float = 0.5262
    skin: float = 0.015
    attack_duration: float = 0.35
    attack_cooldown: float = 0.41
    attack_recovery: float = 0.15
    recoil_velocity: float = 3.75
    recoil_steps: int = 8
    ds_antic: float = 0.1
    ds_time: float = 0.1
    ds_speed: float = 26.0
    ds_recovery: float = 0.25
    ds_land_recovery: float = 0.166666672
    ds_antic_decel: float = 0.8
    ds_antic_vy_min: float = -12.0
    ds_antic_vy_max: float = 12.0
    ds_end_vy: float = -10.0
    pogo_jump_steps: int = 4
    pogo_jumped_steps: int = -20
    bounce_steps: int = 6
    hurt_velocity: float = 15.0
    hurt_vy_ratio: float = 0.5
    hurt_recoil_time: float = 0.2
    hurt_wait: float = 0.1
    hurt_ramp: float = 0.1
    hurt_wait_skip: int = 1
    invul_time: float = 1.0
    cast_antic: float = 0.25
    cast_throw: float = 0.4334
    cast_catch: float = 0.15
    cast_decay: float = 0.9
    cast_decay_ground: float = 0.85
    cast_vy_cap: float = 12.0
    cast_catch_speed: float = 21.0
    cast_catch_decay: float = 0.7
    cast_silk: int = 4
    bind_time: float = 1.4
    bind_decay: float = 0.85
    bind_vy_cap: float = 7.5
    bind_vy_cap_down: float = 12.0
    bind_end_vy: float = -0.25
    bind_silk: int = 9
    bind_break_before: float = 1.2    # a hit in the first this many s of a Bind (the charge) starts BindBreak
    wf_bias_wait: float = 0.0         # world-freeze wait / ramp-up thresholds moved by the timing lanes (Variant)
    wf_bias_up: float = 0.0
    silk_max: int = 9
    lock_decay: float = 0.86
    ledge_steps: int = 4
    land_slop_lo: float = 0.0075
    land_slop_hi: float = 0.004
    input_jump_lag: int = 1
    rdown_halve: int = 0              # RecoilDown halves a rise instead of stopping it (Weighted Anklet)
    # Weighted Anklet (Gameplay asset, docs/facts/1.0.30000/crests.json "weighted_anklet"; HeroController.cs
    # StartRecoil 9615-9621, Recoil 6568-6578, RecoilDown 6655-6672, GetMaxFallVelocity 4866-4872)
    weighted: bool = False            # True: the values below are applied (with_weighted())
    weighted_knockback_mult: float = 0.5
    weighted_invuln_mult: float = 1.3
    weighted_recoil_steps: int = 4
    max_fall_weighted: float = 38.0
    # frame-time jitter model (kin_fit: unscaled gameplay frame times of the bot recordings)
    frame_time_lo: float = 0.016649993    # no frame is shorter (the frame limiter)
    frame_time_hi: float = 0.0170         # p99.99 of the frame time: the rollout's timing lanes run between lo and hi
    frame_time_max: float = 0.018         # the envelope bound: every frame but the hitches is at most this long
    hitch_max: float = 0.040              # and a hitch at most this long (observed max 0.0369 s in 2.83 M frames)
    hitch_rate: float = 2.9e-5            # frames longer than frame_time_max, per frame
    hitches_per_window: int = 2           # most frames above frame_time_max in any 65 frames (recoil + margin)
    # Silkspear phases that end one frame apart with no timer explaining it (the needle's way back): the
    # rollout's variant lanes take each value, [threshold, share of the logged throws]
    # how far the variant lanes move the timer thresholds (Variant); chosen on live i0_000, the fit recording:
    # variant-hull coverage 99.05 / 99.03 / 98.94 % of covered windows at 0.5 / 1 / 2 ms
    timer_bias: float = 0.0005
    alpha_margin: float = 0.01            # phase lanes: the feasible phase interval widened by this (frame drift)
    cast_throw_variants: list = field(default_factory=lambda: [[0.42, 0.5], [0.44, 0.5]])
    cast_catch_variants: list = field(default_factory=lambda: [[0.14, 0.5], [0.16, 0.5]])
    bind_time_variants: list = field(default_factory=list)     # Bind lengths one frame apart, as the cast phases
    jump_heights: list = field(default_factory=list)   # per jump hold length: logged and model apex spread
    scenes: dict = field(default_factory=dict)       # scene -> {"enable": [go names], "disable": [go names]}
    source: dict = field(default_factory=dict)       # key -> provenance note
    fit: dict = field(default_factory=dict)          # kin_fit summary (measured values, residuals, data used)

    VECTOR = ("fdt", "gravity", "run_speed", "jump_speed", "jump_steps", "jump_steps_min", "jump_queue_steps",
              "attack_queue_steps", "tool_queue_steps", "jump_release_mult", "air_hang_gravity", "air_hang_accel",
              "max_fall", "airborne_lift", "half_width", "foot", "head", "skin", "attack_duration", "attack_cooldown",
              "attack_recovery", "recoil_velocity", "recoil_steps", "ds_antic", "ds_time", "ds_speed", "ds_recovery",
              "ds_land_recovery", "ds_antic_decel", "ds_antic_vy_min", "ds_antic_vy_max", "ds_end_vy",
              "pogo_jump_steps", "pogo_jumped_steps", "bounce_steps", "hurt_velocity", "hurt_vy_ratio",
              "hurt_recoil_time", "hurt_wait", "hurt_ramp", "hurt_wait_skip", "invul_time", "cast_antic",
              "cast_throw", "cast_catch", "cast_decay", "cast_decay_ground", "cast_vy_cap", "cast_catch_speed",
              "cast_catch_decay", "cast_silk", "bind_time", "bind_decay", "bind_vy_cap",
              "bind_vy_cap_down", "bind_end_vy", "bind_silk",
              "silk_max", "lock_decay", "ledge_steps", "land_slop_lo", "land_slop_hi", "rdown_halve",
              "bind_break_before", "wf_bias_wait", "wf_bias_up")

    def vector(self) -> np.ndarray:
        return np.array([float(getattr(self, k)) for k in self.VECTOR], dtype=np.float64)

    def scene(self, name: str) -> dict:
        return self.scenes.get(name, {})

    def with_weighted(self, on: bool = True) -> "HeroParams":
        """A copy with the Weighted Anklet equipped (knockback x0.5, i-frames x1.3, nail recoil 4 steps, max fall
        38, RecoilDown halves the rise). Not identified on logs yet: the bot runs never equipped it."""
        p = HeroParams.from_json(self.to_json())
        if not on or self.weighted:
            return p
        p.weighted = True
        p.hurt_velocity = self.hurt_velocity * self.weighted_knockback_mult
        p.invul_time = self.invul_time * self.weighted_invuln_mult
        p.recoil_steps = self.weighted_recoil_steps
        p.max_fall = self.max_fall_weighted
        p.rdown_halve = 1
        return p

    def cast_variant(self, which: str) -> tuple[float, float, float]:
        """(Silkspear throw, catch, Bind) thresholds of a variant: "nominal" (the shipped values), "short" or "long"
        (the shortest or the longest of the logged variants)."""
        if which == "nominal":
            return self.cast_throw, self.cast_catch, self.bind_time
        th = sorted(v[0] for v in self.cast_throw_variants) or [self.cast_throw]
        ca = sorted(v[0] for v in self.cast_catch_variants) or [self.cast_catch]
        bi = sorted(v[0] for v in self.bind_time_variants) or [self.bind_time]
        return (th[0], ca[0], bi[0]) if which == "short" else (th[-1], ca[-1], bi[-1])

    def jitter(self) -> dict:
        return {"frame_time": self.frame_time, "lo": self.frame_time_lo, "hi": self.frame_time_hi,
                "max": self.frame_time_max, "hitch_max": self.hitch_max, "hitch_rate": self.hitch_rate,
                "hitches": self.hitches_per_window}

    def to_json(self) -> dict:
        return asdict(self)

    def save(self, path: str | Path = DEFAULT_PARAMS) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=1, sort_keys=False) + "\n", encoding="utf-8")
        return path

    @classmethod
    def from_json(cls, d: dict) -> "HeroParams":
        names = {f.name for f in fields(cls)}
        unknown = set(d) - names
        if unknown:
            raise ValueError(f"unknown kinematics keys {sorted(unknown)}")
        return cls(**d)

    @classmethod
    def load(cls, path: str | Path = DEFAULT_PARAMS) -> "HeroParams":
        return cls.from_json(json.loads(Path(path).read_text(encoding="utf-8")))


(P_FDT, P_G, P_RUN, P_JUMP, P_JSTEPS, P_JSTEPS_MIN, P_JQ, P_AQ, P_QQ, P_REL, P_AH_G, P_AH_ACC, P_MAXFALL, P_LIFT, P_HW,
 P_FOOT, P_HEAD, P_SKIN, P_ATK_DUR, P_ATK_CD, P_ATK_REC, P_RV, P_RSTEPS, P_DS_ANTIC, P_DS_TIME, P_DS_SPEED, P_DS_REC,
 P_DS_LREC, P_DS_DECEL, P_DS_VYMIN, P_DS_VYMAX, P_DS_ENDVY, P_POGO_J, P_POGO_JD, P_BOUNCE, P_HURT_V, P_HURT_VY,
 P_HURT_T, P_HURT_WAIT, P_HURT_RAMP, P_HURT_SKIP, P_INV_T, P_CAST_ANTIC, P_CAST_THROW, P_CAST_CATCH, P_CAST_DECAY,
 P_CAST_DECAY_G, P_CAST_VYCAP, P_CAST_CSPEED, P_CAST_CDECAY, P_CAST_SILK, P_BIND_T, P_BIND_DECAY, P_BIND_VYCAP,
 P_BIND_VYDOWN, P_BIND_ENDVY, P_BIND_SILK, P_SILK_MAX, P_LOCK_DECAY, P_LEDGE, P_SLOP_LO, P_SLOP_HI, P_RDOWN_HALF,
 P_BIND_BREAK, P_WF_BW, P_WF_BU, NP) = range(67)
assert NP == len(HeroParams.VECTOR)


# ---- terrain --------------------------------------------------------------------------------------------------

class _ShapeView:
    """One TERRAIN shape dict as the solids loop reads it (ssbot.oracle.messages.Shape: kind, float32 verts, radius)."""
    __slots__ = ("kind", "verts", "radius")

    def __init__(self, d: dict):
        self.kind = d["k"]
        v = d["v"]
        self.verts = np.frombuffer(v, dtype="<f4").reshape(-1, 2) if isinstance(v, (bytes, bytearray)) else \
            np.asarray(v, dtype=np.float32).reshape(-1, 2)
        self.radius = float(d.get("r", 0.0))


class _SolidView:
    __slots__ = ("go", "on", "shapes")

    def __init__(self, d: dict):
        self.go, self.on = d["go"], d["on"]
        self.shapes = [_ShapeView(x) for x in d.get("shapes") or ()]


@dataclass(slots=True)
class Terrain2D:
    """Static collision geometry as axis-aligned segments: hseg rows (y, x0, x1) block vertical motion, vseg rows
    (x, y0, y1) horizontal motion. Sloped edges are kept in `slopes` (x0, y0, x1, y1) and not collided yet (none in
    the Bone_05 arena), together with the AABB sides of round shapes (shape_outline), which only the knockback bound
    reads. Built from a TERRAIN message: every outline of every solid that is on (or listed in
    overrides["enable"]) and not listed in overrides["disable"]; the dump is taken at room entry, so arena gates
    that close later are off in it and stale ones on (Bone_05: the "Threaded Bell Gate" pair closes for the fight,
    "Wall" is gone; HeroParams.scenes)."""
    hseg: np.ndarray
    vseg: np.ndarray
    slopes: np.ndarray
    names: list = field(default_factory=list)
    gates: np.ndarray = field(default_factory=lambda: np.zeros((0, 4)))   # AABBs of overrides["enable"] solids
    n_base: tuple = (-1, -1)          # hseg / vseg rows before the gate rows (-1: no gates)
    _grid: np.ndarray | None = field(default=None, repr=False, compare=False)

    def packed(self, width: float = 1.0) -> np.ndarray:
        """The segments and an x-bucket index of them in one float64 array, for the compiled rollout and the
        knockback queries (layout in kin_jit: a bucket lists the floors / ceilings whose x extent, the walls whose x
        and the slopes whose x extent falls in it, with a 0.02 u margin, so a query looks at a handful of segments
        instead of all of them). Built once per terrain."""
        if self._grid is None:
            h = np.ascontiguousarray(self.hseg, dtype=np.float64).reshape(-1, 3)
            v = np.ascontiguousarray(self.vseg, dtype=np.float64).reshape(-1, 3)
            sl = np.ascontiguousarray(self.slopes, dtype=np.float64).reshape(-1, 4)
            xs = np.concatenate([h[:, 1], h[:, 2], v[:, 0], sl[:, 0], sl[:, 2]])
            x0 = float(xs.min()) - 1.0 if len(xs) else 0.0
            nb = int(np.ceil((float(xs.max()) + 1.0 - x0) / width)) + 1 if len(xs) else 0
            b = lambda x: int(np.floor((x - x0) / width))  # noqa: E731

            def csr(ranges: list[tuple[int, int]]) -> tuple[np.ndarray, np.ndarray]:
                lists: list[list[int]] = [[] for _ in range(nb)]
                for j, (lo, hi) in enumerate(ranges):
                    for k in range(max(lo, 0), min(hi, nb - 1) + 1):
                        lists[k].append(j)
                start = np.zeros(nb + 1)
                start[1:] = np.cumsum([len(x) for x in lists])
                return start, np.array([j for x in lists for j in x], dtype=np.float64)

            hst, hix = csr([(b(r[1] - 0.02), b(r[2] + 0.02)) for r in h])
            vst, vix = csr([(b(r[0] - 0.02), b(r[0] + 0.02)) for r in v])
            sst, six = csr([(b(min(r[0], r[2]) - 0.02), b(max(r[0], r[2]) + 0.02)) for r in sl])
            o_h = TT_HEAD
            o_v = o_h + h.size
            o_s = o_v + v.size
            o_hs = o_s + sl.size
            o_hi = o_hs + len(hst)
            o_vs = o_hi + len(hix)
            o_vi = o_vs + len(vst)
            o_ss = o_vi + len(vix)
            o_si = o_ss + len(sst)
            head = [len(h), len(v), nb, x0, 1.0 / width, o_hs, o_hi, o_vs, o_vi, o_v, len(sl), o_s, o_ss, o_si]
            assert len(head) == TT_HEAD
            self._grid = np.ascontiguousarray(np.concatenate([np.array(head, dtype=np.float64), h.ravel(), v.ravel(),
                                                              sl.ravel(), hst, hix, vst, vix, sst, six]))
        return self._grid

    def open(self) -> "Terrain2D":
        """The same scene with the arena gates open (before or after the fight)."""
        if self.n_base[0] < 0:
            return self
        return Terrain2D(self.hseg[:self.n_base[0]], self.vseg[:self.n_base[1]], self.slopes, self.names)

    def inside_gates(self, x: np.ndarray) -> np.ndarray:
        """True where x lies between a gate on its left and one on its right (inside a closed arena)."""
        x = np.asarray(x, dtype=np.float64)
        if len(self.gates) == 0:
            return np.zeros(x.shape, dtype=bool)
        left = (self.gates[:, 2][None, :] <= x[..., None]).any(axis=-1)
        right = (self.gates[:, 0][None, :] >= x[..., None]).any(axis=-1)
        return left & right

    @classmethod
    def empty(cls) -> "Terrain2D":
        z = np.zeros((0, 3))
        return cls(z, z.copy(), np.zeros((0, 4)))

    @classmethod
    def from_boxes(cls, boxes: Iterable[tuple[float, float, float, float]]) -> "Terrain2D":
        """Solid AABBs (x0, y0, x1, y1), for tests and hand-made arenas."""
        outlines = [np.array([[a, b], [c, b], [c, d], [a, d]], dtype=np.float64) for a, b, c, d in boxes]
        return cls.from_outlines(outlines, closed=[True] * len(outlines))

    @classmethod
    def from_outlines(cls, outlines: list[np.ndarray], closed: list[bool], names: list | None = None,
                      rounded: Iterable[tuple[float, float, float, float]] = ()) -> "Terrain2D":
        """rounded: AABBs (x0, y0, x1, y1) of round geometry (circles, capsules, edge radii) whose four sides are
        added to `slopes`: the rollout does not collide them, and the knockback bound switches to its
        contact-projection rule before the path can reach them."""
        h, v, s = [], [], []
        for a, b, c, d in rounded:
            s.extend(((a, b, c, b), (c, b, c, d), (c, d, a, d), (a, d, a, b)))
        for pts, cl in zip(outlines, closed):
            pts = np.asarray(pts, dtype=np.float64)
            n = len(pts)
            if n < 2:
                continue
            for i in range(n if cl else n - 1):
                (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
                if abs(y1 - y0) <= 1e-4 and abs(x1 - x0) > 1e-4:
                    h.append((0.5 * (y0 + y1), min(x0, x1), max(x0, x1)))
                elif abs(x1 - x0) <= 1e-4 and abs(y1 - y0) > 1e-4:
                    v.append((0.5 * (x0 + x1), min(y0, y1), max(y0, y1)))
                elif abs(x1 - x0) > 1e-4:
                    s.append((x0, y0, x1, y1))
        arr = lambda rows, w: np.array(rows, dtype=np.float64).reshape(-1, w)  # noqa: E731
        return cls(arr(h, 3), arr(v, 3), arr(s, 4), list(names or []))

    @staticmethod
    def shape_outline(kind: str, verts: np.ndarray, radius: float = 0.0
                      ) -> tuple[np.ndarray | None, bool, tuple[float, float, float, float] | None]:
        """(outline for the rollout or None, closed, AABB of its round part or None) of one TERRAIN shape
        (oracle/src/SceneDump/ColliderGeometry.cs). Box2D deflects a push along a round surface as along a slope, so
        circles (1 vertex = centre, radius r: the circumscribed octagon, whose flat faces sit at r), capsules (the
        outline is their bounding box, or 2 centres + radius from the physics fallback: that box grown by r) and
        shapes with an edge radius above ROUND_MIN also report their AABB grown by the radius (Bone_05 has none: box,
        edge and poly shapes, radius 0); unknown kinds fail closed as that AABB (a box for the rollout, round for the
        bound)."""
        v = np.asarray(verts, dtype=np.float64).reshape(-1, 2)
        r = max(float(radius or 0.0), 0.0)
        if not len(v):
            return None, False, None
        lo, hi = v.min(axis=0) - r, v.max(axis=0) + r
        aabb = (float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1]))
        box = np.array([[lo[0], lo[1]], [hi[0], lo[1]], [hi[0], hi[1]], [lo[0], hi[1]]])
        if kind == "circle":
            if r <= 0:
                return None, False, None
            ang = np.pi / 8 + np.arange(8) * np.pi / 4
            oct_ = v[0][None, :] + (r / np.cos(np.pi / 8)) * np.stack([np.cos(ang), np.sin(ang)], axis=1)
            return oct_, True, aabb
        if kind == "capsule":
            return box, True, aabb
        if kind in ("box", "poly", "edge"):
            if len(v) < 2:
                return None, False, None
            if r > ROUND_MIN:
                return (box if kind == "box" else v), kind != "edge", aabb
            return v, kind != "edge", None
        return box, True, aabb

    @classmethod
    def from_message(cls, msg, overrides: dict | None = None) -> "Terrain2D":
        """From a TERRAIN payload (RecordingReader.terrain() / OracleLink: the msgpack dict) or anything with
        .solids (ssbot.oracle.messages.Terrain). Round shapes: shape_outline. The dict is read here, not through the
        oracle's message decoder, so the combat packages that roll this model out stay behind the import firewall
        (tests/test_import_firewall.py); only the fields the solids need (go, on, shapes k / v / r) are read."""
        solids = msg.solids if hasattr(msg, "solids") else [_SolidView(x) for x in msg.get("solids", ())]
        ov = overrides or {}
        enable, disable = set(ov.get("enable", ())), set(ov.get("disable", ()))
        parts: dict[bool, tuple[list, list, list, list]] = {False: ([], [], [], []), True: ([], [], [], [])}
        boxes = []
        for sol in solids:
            if sol.go in disable or not (sol.on or sol.go in enable):
                continue
            gate = (not sol.on) and sol.go in enable
            for sh in sol.shapes:
                outline, closed, rnd = cls.shape_outline(sh.kind, sh.verts, getattr(sh, "radius", 0.0))
                if outline is None:
                    continue
                o, c, n, rd = parts[gate]
                o.append(outline)
                c.append(closed)
                n.append(sol.go)
                if rnd is not None:
                    rd.append(rnd)
                if gate:
                    boxes.append((*outline.min(axis=0), *outline.max(axis=0)))
        base = cls.from_outlines(*parts[False])
        if not boxes:
            return base
        g = cls.from_outlines(*parts[True])
        return cls(np.concatenate([base.hseg, g.hseg]), np.concatenate([base.vseg, g.vseg]),
                   np.concatenate([base.slopes, g.slopes]), base.names + g.names, np.array(boxes, dtype=np.float64),
                   (len(base.hseg), len(base.vseg)))

    def crop(self, x0: float, y0: float, x1: float, y1: float) -> "Terrain2D":
        """Only the segments touching the box (a rollout covers at most ~25 u in 0.8 s)."""
        h = self.hseg[(self.hseg[:, 0] >= y0) & (self.hseg[:, 0] <= y1) & (self.hseg[:, 2] >= x0) &
                      (self.hseg[:, 1] <= x1)]
        v = self.vseg[(self.vseg[:, 0] >= x0) & (self.vseg[:, 0] <= x1) & (self.vseg[:, 2] >= y0) &
                      (self.vseg[:, 1] <= y1)]
        return Terrain2D(h, v, self.slopes, self.names)    # gate bookkeeping does not survive a crop

    def arrays(self) -> tuple[np.ndarray, np.ndarray]:
        return self.hseg, self.vseg


def _move_x(px, py, dx, P, vseg):
    """Move the hero boxes by dx, stopping at walls (skin away). Returns (new x, blocked)."""
    nx = px + dx
    if vseg.shape[0] == 0:
        return nx, np.zeros(px.shape, dtype=np.bool_)
    hw, skin = P[P_HW], P[P_SKIN]
    s, y0, y1 = vseg[:, 0][None, :], vseg[:, 1][None, :], vseg[:, 2][None, :]
    bot = (py - P[P_FOOT])[:, None]
    top = (py + P[P_HEAD])[:, None]
    yov = (top > y0 + EPS) & (bot < y1 - EPS)
    d = dx[:, None]
    lim_r = s - skin - hw
    lim_l = s + skin + hw
    hit_r = yov & (d > 0) & (px[:, None] <= lim_r + TOL) & (nx[:, None] > lim_r)
    hit_l = yov & (d < 0) & (px[:, None] >= lim_l - TOL) & (nx[:, None] < lim_l)
    rx = np.where(hit_r, lim_r, np.inf).min(axis=1)
    lx = np.where(hit_l, lim_l, -np.inf).max(axis=1)
    out = np.maximum(np.minimum(nx, rx), lx)
    return out, hit_r.any(axis=1) | hit_l.any(axis=1)


def _move_y(px, py, dy, P, hseg):
    """Move by dy against floors and ceilings. Returns (new y, landed, touched, bumped). A fall that would end
    below the resting height by more than land_slop_lo is stopped there in the same step (Box2D's TOI step: velocity
    zeroed, OnCollisionEnter -> BackOnGround in that step: 270 of 288 landings in the trial run); one that ends
    within [-land_slop_lo, +land_slop_hi] of it keeps its position and velocity and only touches (the contact is made
    and resolved in the next step: the other 18, all with free-flight end heights in [-0.007, +0.0035])."""
    ny = py + dy
    z = np.zeros(px.shape, dtype=np.bool_)
    if hseg.shape[0] == 0:
        return ny, z, z.copy(), z.copy()
    hw, skin, foot, head = P[P_HW], P[P_SKIN], P[P_FOOT], P[P_HEAD]
    s, x0, x1 = hseg[:, 0][None, :], hseg[:, 1][None, :], hseg[:, 2][None, :]
    xov = ((px + hw)[:, None] > x0 + EPS) & ((px - hw)[:, None] < x1 - EPS)
    d = dy[:, None]
    lim_d = s + skin + foot           # body y resting on the segment
    lim_u = s - skin - head           # body y with the head under it
    cross = xov & (d < 0) & (py[:, None] >= lim_d - TOL) & (ny[:, None] < lim_d + P[P_SLOP_HI])
    hit_d = cross & (ny[:, None] < lim_d - P[P_SLOP_LO])
    touch = cross & ~hit_d
    hit_u = xov & (d > 0) & (py[:, None] <= lim_u + TOL) & (ny[:, None] > lim_u)
    dn = np.where(hit_d, lim_d, -np.inf).max(axis=1)
    up = np.where(hit_u, lim_u, np.inf).min(axis=1)
    out = np.minimum(np.maximum(ny, dn), up)
    landed = hit_d.any(axis=1)
    return out, landed, touch.any(axis=1) & ~landed, hit_u.any(axis=1)


def _on_ground(px, py, P, hseg):
    if hseg.shape[0] == 0:
        return np.zeros(px.shape, dtype=np.bool_)
    hw = P[P_HW]
    s, x0, x1 = hseg[:, 0][None, :], hseg[:, 1][None, :], hseg[:, 2][None, :]
    xov = ((px + hw)[:, None] > x0 + EPS) & ((px - hw)[:, None] < x1 - EPS)
    gap = (py - P[P_FOOT])[:, None] - (s + P[P_SKIN])
    return (xov & (gap >= -GTOL) & (gap <= GTOL)).any(axis=1)


# ---- the model: one physics step, one Update ------------------------------------------------------------------

def _f32(a):
    """Game timers are float32 sums of float32 frame times (the logged dt / udt are float32 already); doing the same
    keeps threshold crossings (6 or 7 antic frames, 13 / 14 / 15 hit-stop frames) on the same frame as the game."""
    return a.astype(np.float32).astype(np.float64)


def _ge32(a, c):
    return a.astype(np.float32) >= np.float32(c)


def _gt32(a, c):
    return a.astype(np.float32) > np.float32(c)


def _isin(mode, codes):
    out = np.zeros(mode.shape, dtype=np.bool_)
    for c in codes:
        out |= mode == c
    return out


def _fixed_step(X, P, hseg, vseg):
    """HeroController.FixedUpdate for the modelled modes plus one Rigidbody2D step, for every column of X."""
    fdt = P[P_FDT]
    X[QX] = X[PX]
    X[QY] = X[PY]
    mode = X[MODE]
    normal = mode == M_NORMAL
    relinq = _isin(mode, RELINQUISHED)
    noinp = _isin(mode, NO_INPUT)

    # nail recoil step counter (top of FixedUpdate)
    rec = X[RDIR] != 0
    over = rec & (X[RSTEPS] <= 0)
    X[RSTEPS] = np.where(rec & ~over, X[RSTEPS] - 1, X[RSTEPS])
    X[RDIR] = np.where(over, 0.0, X[RDIR])

    # NORMAL: DoMovement -> Move (velocity x straight from the input), facing, recoil, Jump()
    mv = np.where((X[DS_REC] >= 0) & (X[GROUND] > 0), 0.0, X[MOVE])
    vx = np.where(normal, mv * P[P_RUN], X[VX])
    can_turn = normal & ~((X[ATTACKING] > 0) & (X[ATK_T] < P[P_ATK_REC]))
    turn = can_turn & (mv != 0) & (np.sign(mv) != X[FACE])
    X[FACE] = np.where(turn, np.sign(mv), X[FACE])
    X[ATTACKING] = np.where(turn, 0.0, X[ATTACKING])
    rv = P[P_RV]
    rl = normal & (X[RDIR] < 0)
    rr = normal & (X[RDIR] > 0)
    vx = np.where(rl, np.where(vx > 0, -rv, vx - rv), vx)
    vx = np.where(rr, np.where(vx < 0, rv, vx + rv), vx)
    vy = X[VY].copy()
    jmp = normal & (X[JUMPING] > 0)
    rise = jmp & (X[JSTEPS] <= P[P_JSTEPS])
    vy = np.where(rise, P[P_JUMP], vy)
    X[JSTEPS] = np.where(rise, X[JSTEPS] + 1, np.where(jmp, 0.0, X[JSTEPS]))
    X[JDSTEPS] = np.where(rise, X[JDSTEPS] + 1, X[JDSTEPS])
    X[JUMPING] = np.where(jmp & ~rise, 0.0, X[JUMPING])
    bounce = X[BOUNCE] >= 0
    X[BOUNCE] = np.where(bounce & (X[BOUNCE] <= P[P_BOUNCE]), X[BOUNCE] + 1, np.where(bounce, -1.0, X[BOUNCE]))

    # DS_SPIKE: Downspike() (timer in FixedUpdate)
    sp = mode == M_DS_SPIKE
    fin = sp & _gt32(X[MODE_T], P[P_DS_TIME])
    thr = sp & ~fin
    vx = np.where(thr, X[DS_HS], vx)
    vy = np.where(thr, -P[P_DS_SPEED], vy)
    X[MODE_T] = np.where(thr, _f32(X[MODE_T] + np.float32(fdt)), X[MODE_T])
    vy = np.where(fin, P[P_DS_ENDVY], vy)
    X[GS] = np.where(fin, 1.0, X[GS])
    X[DS_REC] = np.where(fin, 0.0, X[DS_REC])
    X[MODE] = np.where(fin, M_NORMAL, X[MODE])
    mode = X[MODE]
    relinq = _isin(mode, RELINQUISHED)

    # DS_ANTIC: v *= 0.8 while the antic timer is below the antic time (gravity was switched off at the attack)
    an = (mode == M_DS_ANTIC) & ~_ge32(X[MODE_T], P[P_DS_ANTIC])
    vx = np.where(an, vx * P[P_DS_DECEL], vx)
    vy = np.where(an, vy * P[P_DS_DECEL], vy)
    # damage: frozen in place, then the recoil vector
    fr = mode == M_HURT_FREEZE
    hr = mode == M_HURT_RECOIL
    vx = np.where(fr, 0.0, np.where(hr, X[HVX], vx))
    vy = np.where(fr, 0.0, np.where(hr, X[HVY], vy))
    # Silkspear: antic (ground: still; air: v *= cast_decay per step), throw (still), catch (pulled back, decaying)
    ca = mode == M_CAST
    air = X[GROUND] <= 0
    ph = X[PHASE]
    c0 = ca & (ph == 0)
    vx = np.where(c0, vx * np.where(air, P[P_CAST_DECAY], P[P_CAST_DECAY_G]), vx)
    vy = np.where(c0, np.where(air, vy * P[P_CAST_DECAY], 0.0), vy)
    c1 = ca & (ph == 1)
    vx = np.where(c1, 0.0, vx)
    vy = np.where(c1, 0.0, vy)
    vx = np.where(ca & (ph == 2), vx * P[P_CAST_CDECAY], vx)
    bi = mode == M_BIND
    vx = np.where(bi, np.where(air, vx * P[P_BIND_DECAY], 0.0), vx)
    vy = np.where(bi, np.where(air, vy * P[P_BIND_DECAY], 0.0), vy)
    lk = mode == M_LOCKED
    vx = np.where(lk, vx * P[P_LOCK_DECAY], vx)

    # terminal velocity (not while relinquished), queues, air hang
    vy = np.where(~relinq & (vy < -P[P_MAXFALL]), -P[P_MAXFALL], vy)
    X[JQ] = np.where(X[JQ] >= 0, X[JQ] + 1, X[JQ])
    X[AQ] = np.where(X[AQ] >= 0, X[AQ] + 1, X[AQ])
    X[QQ] = np.where(X[QQ] >= 0, X[QQ] + 1, X[QQ])
    ground = X[GROUND] > 0
    hang = (X[AIRHANG] <= 0) & ~ground & (vy < 0)
    X[GS] = np.where(hang & ~relinq & ~noinp, P[P_AH_G], X[GS])
    X[AIRHANG] = np.where(hang, 1.0, np.where(ground, 0.0, X[AIRHANG]))
    ctl = ~relinq & ~noinp
    gs = X[GS]
    gs = np.where(ctl & (gs < 1.0), gs + P[P_AH_ACC] * fdt, gs)
    gs = np.where(ctl & (gs < 1.0) & (X[JHELD] <= 0), 1.0, gs)
    X[GS] = np.minimum(gs, 1.0)
    X[LEDGE] = np.maximum(X[LEDGE] - 1, 0.0)

    # Rigidbody2D step: v += g dt, contact from a touch in the last step, then move with collision
    vy = vy - P[P_G] * X[GS] * fdt
    pend = X[TOUCH] > 0
    under = _on_ground(X[PX], X[PY], P, hseg)
    resolve = pend & (vy <= 0) & under
    # contacts are found before the move: a hero standing at the start of the step does not sink in it, even if
    # the step carries the box past the end of the floor (walking off a ledge falls from the next step on)
    vy = np.where(resolve | ((X[GROUND] > 0) & under & (vy < 0)), 0.0, vy)
    nx, hitx = _move_x(X[PX], X[PY], vx * fdt, P, vseg)
    vx = np.where(hitx, 0.0, vx)
    ny, landed, touched, bumped = _move_y(nx, X[PY], vy * fdt, P, hseg)
    vy = np.where(landed | bumped, 0.0, vy)
    X[PX] = nx
    X[PY] = ny
    X[SX] = nx
    X[SY] = ny
    X[VX] = vx
    X[VY] = vy
    X[TOUCH] = touched.astype(np.float64)
    was = X[GROUND] > 0
    stay = was & (vy <= 0) & _on_ground(nx, ny, P, hseg)
    lands = (landed | resolve) & ~noinp            # BackOnGround is not called in hero_state no_input
    now = stay | lands
    X[GROUND] = now.astype(np.float64)
    X[JUMPING] = np.where(lands, 0.0, X[JUMPING])
    X[JSTEPS] = np.where(lands, 0.0, X[JSTEPS])
    X[LEDGE] = np.where(was & ~now & (X[JUMPING] <= 0) & (X[MODE] == M_NORMAL), P[P_LEDGE], X[LEDGE])
    # a downspike that reaches the floor ends there (HandleCollisionTouching -> FinishDownspike)
    # (also when the spike starts on the floor: OnCollisionStay reports the same bottom contact)
    land_sp = (landed | resolve | (under & (X[GROUND] > 0))) & (X[MODE] == M_DS_SPIKE)
    X[MODE] = np.where(land_sp, M_NORMAL, X[MODE])
    X[DS_REC] = np.where(land_sp, 0.0, X[DS_REC])
    X[GS] = np.where(land_sp, 1.0, X[GS])
    X[VY] = np.where(land_sp, P[P_DS_ENDVY], X[VY])
    # landing into idle ends a downspike recovery at once, into a run it lasts DOWNSPIKE_LAND_RECOVERY_TIME
    # (HeroAnimationController.UpdateState, airborne -> idle / run): decided in this frame's Update, on the input
    # read there (the move input of the spike's own frames is stale: LookForInput does not run while relinquished)
    X[LANDQ] = np.where((lands | land_sp) & ~was, 1.0, X[LANDQ])


def _wf_start(X, on, preset):
    """GameManager.FreezeMoment started in this frame (other than the hero's own hit-stop): its coroutine runs to the
    first yield at once (SetTimeScale ramp down: scale lerp(1, target, 0) = 1; with no ramp down the target at once
    and the wait loop's first step)."""
    down, wait, up, tgt = preset
    X[WF_DOWN] = np.where(on, down, X[WF_DOWN])
    X[WF_WAIT] = np.where(on, wait, X[WF_WAIT])
    X[WF_UP] = np.where(on, up, X[WF_UP])
    X[WF_TGT] = np.where(on, tgt, X[WF_TGT])
    X[WF_T] = np.where(on, 0.0, X[WF_T])
    X[WF_PH] = np.where(on, 10.0 if down > 0 else 11.0, X[WF_PH])
    X[WF_S] = np.where(on, 1.0 if down > 0 else float(np.float32(tgt)), X[WF_S])


def _lerp32(a, b, t):
    """Mathf.Lerp in float32 (t clamped to [0, 1])."""
    a32, b32 = a.astype(np.float32), b.astype(np.float32)
    t32 = np.clip(t, 0.0, 1.0).astype(np.float32)
    return (a32 + (b32 - a32) * t32).astype(np.float64)


def _wf_step(X, udt, P):
    """One frame of the world freeze coroutine (after Update): ramp down, wait, ramp up, each a float32 timer of
    unscaled time; the lanes move the wait / ramp-up thresholds by P_WF_BW / P_WF_BU."""
    ph = X[WF_PH]
    fresh = ph >= 10
    X[WF_PH] = np.where(fresh, ph - 10, ph)
    ph = np.where(fresh, -2.0, X[WF_PH])          # started this frame: no step
    t = np.where(ph >= 0, _f32(X[WF_T] + udt), X[WF_T])
    tgt = X[WF_TGT]
    one = np.ones_like(tgt)
    d0 = ph == 0
    end0 = d0 & ~(t.astype(np.float32) < X[WF_DOWN].astype(np.float32))
    X[WF_S] = np.where(d0 & ~end0, _lerp32(one, tgt, t / np.maximum(X[WF_DOWN], 1e-12)), X[WF_S])
    X[WF_S] = np.where(end0, _f32(tgt), X[WF_S])
    w1 = ph == 1
    end1 = w1 & _ge32(t, X[WF_WAIT] + P[P_WF_BW])
    up0 = end1 & (X[WF_UP] <= 0)
    X[WF_S] = np.where(end1, np.where(up0, 1.0, _f32(tgt)), X[WF_S])
    u2 = ph == 2
    end2 = u2 & _ge32(t, X[WF_UP] + P[P_WF_BU])
    X[WF_S] = np.where(u2 & ~end2, _lerp32(tgt, one, t / np.maximum(X[WF_UP], 1e-12)), X[WF_S])
    X[WF_S] = np.where(end2, 1.0, X[WF_S])
    X[WF_T] = np.where(end0 | end1, 0.0, np.where(ph >= 0, t, X[WF_T]))
    X[WF_PH] = np.where(end0, 1.0, np.where(end1, np.where(up0, -1.0, 2.0), np.where(end2, -1.0, X[WF_PH])))


def _apply_events(X, ev, P):
    """Contact events of this frame (after its physics steps)."""
    mode = X[MODE]
    # a hit during the Bind charge also starts GameManager's BindBreak freeze (22 of 22 logged hits in the charge,
    # 0 of 1 in the burst; the Bind FSM calls FreezeMoment(BindBreak))
    bb = ((ev & (EV_HURT_L | EV_HURT_R)) != 0) & (mode == M_BIND) & (X[MODE_T] < P[P_BIND_BREAK])
    for bit in WF_ORDER:
        _wf_start(X, ((ev & bit) != 0) | (bb if bit == EV_FZ_BIND_BREAK else False), FREEZE_PRESETS[bit])
    relinq = _isin(mode, RELINQUISHED)
    rec_ok = (X[RDIR] == 0) & ~relinq & ~_isin(mode, NO_INPUT)
    for bit, d in ((EV_RECOIL_L, -1.0), (EV_RECOIL_R, 1.0)):
        on = ((ev & bit) != 0) & rec_ok
        X[RDIR] = np.where(on, d, X[RDIR])
        X[RSTEPS] = np.where(on, P[P_RSTEPS], X[RSTEPS])
        X[VX] = np.where(on, d * P[P_RV], X[VX])
    # HeroController.RecoilDown (an up slash that hit): CancelJump, rising velocity cut to RECOIL_DOWN_VELOCITY 0
    # (halved instead with the Weighted Anklet)
    down = ((ev & EV_RECOIL_DOWN) != 0) & ~relinq
    X[JUMPING] = np.where(down, 0.0, X[JUMPING])
    X[JSTEPS] = np.where(down, 0.0, X[JSTEPS])
    X[VY] = np.where(down & (X[VY] > 0), X[VY] * 0.5 if P[P_RDOWN_HALF] > 0 else 0.0, X[VY])
    pogo = (ev & EV_POGO) != 0
    X[MODE] = np.where(pogo, M_NORMAL, X[MODE])
    X[JUMPING] = np.where(pogo, 1.0, X[JUMPING])
    X[JSTEPS] = np.where(pogo, P[P_POGO_J], X[JSTEPS])
    X[JDSTEPS] = np.where(pogo, P[P_POGO_JD], X[JDSTEPS])
    X[BOUNCE] = np.where(pogo, 0.0, X[BOUNCE])
    X[DS_REC] = np.where(pogo, 0.0, X[DS_REC])
    X[GS] = np.where(pogo, 1.0, X[GS])
    X[VY] = np.where(pogo, P[P_DS_ENDVY], X[VY])
    X[PY] = np.where(pogo & (X[GROUND] > 0), X[PY] + P[P_LIFT], X[PY])
    X[GROUND] = np.where(pogo, 0.0, X[GROUND])
    X[JQ] = np.where(pogo, -1.0, X[JQ])
    for bit, side in ((EV_HURT_L, -1.0), (EV_HURT_R, 1.0)):
        on = (ev & bit) != 0
        X[MODE] = np.where(on, M_HURT_FREEZE, X[MODE])
        X[MODE_T] = np.where(on, 0.0, X[MODE_T])
        X[MODE_N] = np.where(on, 0.0, X[MODE_N])
        X[HVX] = np.where(on, -side * P[P_HURT_V], X[HVX])
        X[HVY] = np.where(on, P[P_HURT_V] * P[P_HURT_VY], X[HVY])
        X[FACE] = np.where(on, side, X[FACE])
        X[VX] = np.where(on, 0.0, X[VX])
        X[VY] = np.where(on, 0.0, X[VY])
        X[GS] = np.where(on, 0.0, X[GS])
        X[RDIR] = np.where(on, 0.0, X[RDIR])
        X[ATTACKING] = np.where(on, 0.0, X[ATTACKING])
        X[JUMPING] = np.where(on, 0.0, X[JUMPING])
        X[GROUND] = np.where(on, 0.0, X[GROUND])
        X[INV_T] = np.where(on, P[P_INV_T], X[INV_T])
        X[PHASE] = np.where(on, 0.0, X[PHASE])
        X[TS] = np.where(on, 0.0, X[TS])
    X[SILK] = np.where((ev & EV_SILK) != 0, np.minimum(X[SILK] + 1, P[P_SILK_MAX]), X[SILK])
    lock = (ev & EV_LOCK) != 0
    X[MODE] = np.where(lock, M_LOCKED, X[MODE])
    X[MODE_T] = np.where(lock, 0.0, X[MODE_T])
    unlock = ((ev & EV_UNLOCK) != 0) & (X[MODE] == M_LOCKED)
    X[MODE] = np.where(unlock, M_NORMAL, X[MODE])


def _hero_jump(X, go, P):
    X[JUMPING] = np.where(go, 1.0, X[JUMPING])
    X[JSTEPS] = np.where(go, 0.0, X[JSTEPS])
    X[JDSTEPS] = np.where(go, 0.0, X[JDSTEPS])
    X[JQ] = np.where(go, -1.0, X[JQ])
    X[DS_REC] = np.where(go, -1.0, X[DS_REC])
    lift = go & (X[GROUND] > 0)
    X[VY] = np.where(lift & (X[VY] < 0), 0.0, X[VY])
    X[PY] = np.where(lift, X[PY] + P[P_LIFT], X[PY])
    X[GROUND] = np.where(go, 0.0, X[GROUND])
    X[LEDGE] = np.where(go, 0.0, X[LEDGE])
    X[ATTACKING] = np.where(go & (X[ATTACKING] > 0) & (X[ATK_T] >= P[P_ATK_REC]), 0.0, X[ATTACKING])


def _do_attack(X, go, mask, P):
    """DoAttack: down (in the air, Hunter: DownSpike type) or a slash; DidAttack sets the cooldown."""
    want = np.where((mask & B_RIGHT) != 0, 1.0, np.where((mask & B_LEFT) != 0, -1.0, 0.0))
    X[FACE] = np.where(go & (want != 0), want, X[FACE])            # TrySetCorrectFacing(force: true)
    down = go & ((mask & B_UP) == 0) & ((mask & B_DOWN) != 0) & (X[GROUND] <= 0)
    slash = go & ~down
    X[ATTACKING] = np.where(slash, 1.0, X[ATTACKING])
    X[ATK_T] = np.where(go, 0.0, X[ATK_T])
    X[ATK_CD] = np.where(go, P[P_ATK_CD], X[ATK_CD])
    X[AQ] = np.where(go, -1.0, X[AQ])
    X[MODE] = np.where(down, M_DS_ANTIC, X[MODE])
    X[MODE_T] = np.where(down, 0.0, X[MODE_T])
    X[DS_HS] = np.where(down, X[FACE] * P[P_DS_SPEED], X[DS_HS])
    X[VY] = np.where(down, np.clip(X[VY], P[P_DS_VYMIN], P[P_DS_VYMAX]), X[VY])
    X[GS] = np.where(down, 0.0, X[GS])
    X[JUMPING] = np.where(down, 0.0, X[JUMPING])
    X[JSTEPS] = np.where(down, 0.0, X[JSTEPS])


def _update(X, mask, ev, dt, udt, P):
    """HeroController.Update (and the Spell / tool FSM entries the buttons start) for one rendered frame."""
    mode = X[MODE]
    mode0 = mode.copy()              # FSM-driven modes (cast, bind) count from the frame after their entry
    prev = X[PREV].astype(np.int64)
    pressed = mask & ~prev
    normal = mode == M_NORMAL
    noinp = _isin(mode, NO_INPUT)
    accept = normal | noinp          # LookForInput runs in no_input too (acceptingInput stays true in damage recoil)

    # LookForInput: move, jump release, queue resets
    move = np.where((mask & B_RIGHT) != 0, 1.0, 0.0) - np.where((mask & B_LEFT) != 0, 1.0, 0.0)
    X[MOVE] = np.where(accept, move, X[MOVE])
    jheld = (mask & B_JUMP) != 0
    X[JHELD] = np.where(accept, jheld.astype(np.float64), X[JHELD])
    rel = accept & ~jheld
    cut = rel & (X[VY] > 0) & (X[JDSTEPS] >= P[P_JSTEPS_MIN])
    X[VY] = np.where(cut, X[VY] * P[P_REL], X[VY])
    X[JUMPING] = np.where(cut, 0.0, X[JUMPING])
    X[JSTEPS] = np.where(cut, 0.0, X[JSTEPS])
    X[JQ] = np.where(rel, -1.0, X[JQ])
    X[AQ] = np.where(accept & ((mask & B_ATTACK) == 0), -1.0, X[AQ])
    X[QQ] = np.where(accept & ((mask & B_QUICKCAST) == 0), -1.0, X[QQ])
    X[DS_REC] = np.where((X[LANDQ] > 0) & (X[MOVE] == 0), -1.0, X[DS_REC])
    X[LANDQ] = 0.0

    # hero_state branch: in no_input the damage recoil times out here (recoilTimer < RECOIL_DURATION ? += dt :
    # CancelDamageRecoil: v = 0, gravity back, control back), before LookForQueueInput can start a queued action;
    # otherwise the attack timer runs
    hr = mode == M_HURT_RECOIL
    done = hr & _ge32(X[MODE_T], P[P_HURT_T])
    X[MODE_T] = np.where(hr & ~done, _f32(X[MODE_T] + dt), X[MODE_T])
    X[MODE] = np.where(done, M_NORMAL, X[MODE])
    X[VX] = np.where(done, 0.0, X[VX])
    X[VY] = np.where(done, 0.0, X[VY])
    X[GS] = np.where(done, 1.0, X[GS])
    atk = normal & (X[ATTACKING] > 0)
    X[ATK_T] = np.where(atk, _f32(X[ATK_T] + dt), X[ATK_T])
    X[ATTACKING] = np.where(atk & _ge32(X[ATK_T], P[P_ATK_DUR]), 0.0, X[ATTACKING])

    # LookForQueueInput: a press that cannot act now is queued whatever the state (the queue runs in steps)
    normal = X[MODE] == M_NORMAL
    ground = X[GROUND] > 0
    can_jump = normal & (X[JUMPING] <= 0) & (X[BOUNCE] < 0) & (X[DS_REC] < 0) & (ground | (X[LEDGE] > 0))
    jp = (pressed & B_JUMP) != 0
    go = jp & can_jump
    X[JQ] = np.where(jp & ~can_jump, 0.0, X[JQ])
    _hero_jump(X, go, P)
    can_atk_action = normal & (X[ATTACKING] <= 0)
    downish = ((mask & B_DOWN) != 0) & ((mask & B_UP) == 0)
    can_down = (X[BOUNCE] < 0) & (X[DS_REC] < 0)
    # a Bind pressed in the same frame wins over the attack (its FSM takes control first; live run: 2 of 2)
    bind_first = normal & ((pressed & B_BIND) != 0) & (X[SILK] >= P[P_BIND_SILK])
    can_attack = can_atk_action & (X[ATK_CD] <= 0) & (~downish | can_down) & ~bind_first
    ap = (pressed & B_ATTACK) != 0
    go = ap & can_attack
    X[AQ] = np.where(ap & ~can_attack, 0.0, X[AQ])
    _do_attack(X, go, mask, P)
    mode = X[MODE]
    normal = mode == M_NORMAL
    # Silkspear (ThrowTool -> Spell FSM): a press, or a queued one (tool queue 5 steps) still held; it also cancels a
    # down spike (4 of 158 logged casts started there: FinishDownspike first, so v = (0, -10) before the cast law)
    qp = (pressed & B_QUICKCAST) != 0
    qheld = (mask & B_QUICKCAST) != 0
    queued = qheld & (X[QQ] >= 0) & (X[QQ] <= P[P_QQ])
    spike = mode == M_DS_SPIKE
    able = (normal & (X[ATTACKING] <= 0)) | spike
    cast = able & (qp | queued) & (X[SILK] >= P[P_CAST_SILK])
    X[QQ] = np.where(qp & ~cast, 0.0, np.where(cast, -1.0, X[QQ]))
    X[VX] = np.where(cast & spike, 0.0, X[VX])
    X[VY] = np.where(cast & spike, P[P_DS_ENDVY], X[VY])
    X[GROUND] = np.where(cast & spike, 0.0, X[GROUND])
    want = np.where((mask & B_RIGHT) != 0, 1.0, np.where((mask & B_LEFT) != 0, -1.0, 0.0))
    X[FACE] = np.where(cast & (want != 0), want, X[FACE])
    X[MODE] = np.where(cast, M_CAST, X[MODE])
    X[MODE_T] = np.where(cast, 0.0, X[MODE_T])
    X[PHASE] = np.where(cast, 0.0, X[PHASE])
    X[SILK] = np.where(cast, X[SILK] - P[P_CAST_SILK], X[SILK])
    X[GS] = np.where(cast, 0.0, X[GS])
    X[JUMPING] = np.where(cast, 0.0, X[JUMPING])
    cair = cast & (X[GROUND] <= 0)
    X[VX] = np.where(cast, X[VX] * np.where(cair, P[P_CAST_DECAY], P[P_CAST_DECAY_G]), X[VX])
    X[VY] = np.where(cast, np.where(cair, np.clip(X[VY], -P[P_CAST_VYCAP], P[P_CAST_VYCAP]) * P[P_CAST_DECAY], 0.0),
                     X[VY])
    normal = X[MODE] == M_NORMAL
    ground = X[GROUND] > 0
    can_jump = normal & (X[JUMPING] <= 0) & (X[BOUNCE] < 0) & (X[DS_REC] < 0) & (ground | (X[LEDGE] > 0))
    go = normal & jheld & (X[JQ] >= 0) & (X[JQ] <= P[P_JQ]) & can_jump
    _hero_jump(X, go, P)
    can_attack = normal & (X[ATTACKING] <= 0) & (X[ATK_CD] <= 0) & (~downish | can_down) & ~bind_first
    go = normal & ((mask & B_ATTACK) != 0) & (X[AQ] >= 0) & (X[AQ] <= P[P_AQ]) & can_attack
    _do_attack(X, go, mask, P)
    normal = X[MODE] == M_NORMAL
    bind = normal & ((pressed & B_BIND) != 0) & (X[SILK] >= P[P_BIND_SILK])
    X[MODE] = np.where(bind, M_BIND, X[MODE])
    X[MODE_T] = np.where(bind, 0.0, X[MODE_T])
    X[SILK] = np.where(bind, X[SILK] - P[P_BIND_SILK], X[SILK])
    X[GS] = np.where(bind, 0.0, X[GS])
    X[JUMPING] = np.where(bind, 0.0, X[JUMPING])
    X[ATTACKING] = np.where(bind, 0.0, X[ATTACKING])
    bair = bind & (X[GROUND] <= 0)
    X[VX] = np.where(bind, np.where(bair, X[VX] * P[P_BIND_DECAY], 0.0), X[VX])
    X[VY] = np.where(bind, np.where(bair, np.clip(X[VY], -P[P_BIND_VYDOWN], P[P_BIND_VYCAP]) * P[P_BIND_DECAY], 0.0),
                     X[VY])

    # timers (float32, as the game keeps them)
    X[ATK_CD] = np.where(X[ATK_CD] > 0, _f32(X[ATK_CD] - dt), X[ATK_CD])
    rec = X[DS_REC] >= 0
    ground = X[GROUND] > 0
    end = rec & np.where(ground, _ge32(X[DS_REC], P[P_DS_LREC]), _ge32(X[DS_REC], P[P_DS_REC]))
    X[DS_REC] = np.where(end, -1.0, np.where(rec, _f32(X[DS_REC] + dt), X[DS_REC]))
    mode = X[MODE]
    an = mode == M_DS_ANTIC
    to_spike = an & _ge32(X[MODE_T], P[P_DS_ANTIC])
    X[MODE] = np.where(to_spike, M_DS_SPIKE, X[MODE])
    X[MODE_T] = np.where(to_spike, 0.0, np.where(an, _f32(X[MODE_T] + dt), X[MODE_T]))
    # damage hit-stop (GameManager.FreezeMoment, unscaled time): the wait loop sums udt from the second frame
    # after the hit, then SetTimeScale ramps the scale back to 1; the recoil starts in the frame it reaches 1
    fr = mode == M_HURT_FREEZE
    wait = fr & (X[PHASE] == 0) & (X[MODE_N] >= P[P_HURT_SKIP] + 1)
    X[MODE_T] = np.where(wait, _f32(X[MODE_T] + udt), X[MODE_T])
    wdone = wait & _ge32(X[MODE_T], P[P_HURT_WAIT])
    X[PHASE] = np.where(wdone, 1.0, X[PHASE])
    X[MODE_T] = np.where(wdone, 0.0, X[MODE_T])
    ramp = fr & (X[PHASE] == 1) & ~wdone
    X[MODE_T] = np.where(ramp, _f32(X[MODE_T] + udt), X[MODE_T])
    X[TS] = np.where(ramp, np.minimum(X[MODE_T] / P[P_HURT_RAMP], 1.0), X[TS])
    rdone = ramp & _ge32(X[MODE_T], P[P_HURT_RAMP])
    X[TS] = np.where(rdone, 1.0, X[TS])
    X[MODE] = np.where(rdone, M_HURT_RECOIL, X[MODE])
    X[MODE_T] = np.where(rdone, 0.0, X[MODE_T])
    X[MODE_N] = np.where(fr, X[MODE_N] + 1, X[MODE_N])
    # Silkspear phases (FSM states with their own float32 timers, counted from the frame after entry)
    ca = mode0 == M_CAST
    X[MODE_T] = np.where(ca, _f32(X[MODE_T] + dt), X[MODE_T])
    ph = X[PHASE].copy()
    to1 = ca & (ph == 0) & _ge32(X[MODE_T], P[P_CAST_ANTIC])
    X[PHASE] = np.where(to1, 1.0, X[PHASE])
    X[MODE_T] = np.where(to1, 0.0, X[MODE_T])
    X[VX] = np.where(to1, 0.0, X[VX])
    X[VY] = np.where(to1, 0.0, X[VY])
    early = ((ev & EV_CATCH) != 0) & (ph < 2)
    to2 = ca & (((ph == 1) & _ge32(X[MODE_T], P[P_CAST_THROW])) | early)
    X[PHASE] = np.where(to2, 2.0, X[PHASE])
    X[MODE_T] = np.where(to2, 0.0, X[MODE_T])
    X[VX] = np.where(to2, -X[FACE] * P[P_CAST_CSPEED], X[VX])
    X[VY] = np.where(to2, 0.0, X[VY])
    X[GS] = np.where(to2, 1.0, X[GS])
    ca_end = ca & (ph == 2) & _ge32(X[MODE_T], P[P_CAST_CATCH])
    X[MODE] = np.where(ca_end, M_NORMAL, X[MODE])
    X[GS] = np.where(ca_end, 1.0, X[GS])
    bi = mode0 == M_BIND
    X[MODE_T] = np.where(bi, _f32(X[MODE_T] + dt), X[MODE_T])
    bi_end = bi & _ge32(X[MODE_T], P[P_BIND_T])
    X[MODE] = np.where(bi_end, M_NORMAL, X[MODE])
    X[VY] = np.where(bi_end, P[P_BIND_ENDVY], X[VY])
    X[GS] = np.where(bi_end, 1.0, X[GS])
    # control is back: the move input is read again before the next step
    back = ca_end | bi_end
    X[MOVE] = np.where(back, move, X[MOVE])
    X[JHELD] = np.where(back, jheld.astype(np.float64), X[JHELD])
    X[MODE_T] = np.where(X[MODE] == M_LOCKED, _f32(X[MODE_T] + dt), X[MODE_T])
    X[INV_T] = np.maximum(_f32(X[INV_T] - dt), 0.0)
    X[PREV] = mask.astype(np.float64)
    _wf_step(X, udt, P)


def _flags(X) -> np.ndarray:
    mode = X[MODE]
    f = np.zeros(X.shape[1], dtype=np.int32)
    f |= np.where(X[GROUND] > 0, F_GROUND, 0)
    f |= np.where(X[JUMPING] > 0, F_JUMPING, 0)
    f |= np.where(X[ATTACKING] > 0, F_ATTACKING, 0)
    f |= np.where(X[RDIR] != 0, F_RECOIL, 0)
    f |= np.where(_isin(mode, RELINQUISHED), F_RELINQ, 0)
    f |= np.where((X[INV_T] > 0) | _isin(mode, NO_INPUT), F_INVULN, 0)
    f |= np.where(_isin(mode, NO_INPUT), F_NO_INPUT, 0)
    return f


def _simulate(S0, masks, events, dts, fss, udts, P, hseg, vseg):
    """Core loop (array code only, numba-compilable). S0 [K, N]; masks/events [N, T] int64; udts [N, T] unscaled
    frame times; dts / fss [N, T] logged scaled dt and physics steps, or [N, 0] for nominal timing (dt = udt times the
    model's own time scale, steps from the accumulated phase). Returns phys, render, vel [N, T+1, 2], mode, flags
    [N, T+1] and the final state."""
    X = S0.copy()
    n, T = masks.shape
    phys = np.empty((n, T + 1, 2))
    rend = np.empty((n, T + 1, 2))
    vel = np.empty((n, T + 1, 2))
    modes = np.empty((n, T + 1), dtype=np.int32)
    flags = np.empty((n, T + 1), dtype=np.int32)
    logged = dts.shape[1] == T
    fdt = P[P_FDT]
    for t in range(T + 1):
        if t > 0:
            m = masks[:, t - 1]
            ev = events[:, t - 1]
            udt = udts[:, t - 1]
            if logged:
                dt = dts[:, t - 1]
                steps = fss[:, t - 1].astype(np.int64)
                X[ALPHA] = X[ALPHA] + dt / fdt - steps
            else:
                dt = _f32(udt * np.where(X[WF_S] == 1.0, X[TS], X[TS] * X[WF_S]))
                a = X[ALPHA] + dt / fdt
                steps = np.floor(a + 1e-9).astype(np.int64)
                X[ALPHA] = a - steps
            X[ALPHA] = np.minimum(np.maximum(X[ALPHA], 0.0), 1.0)
            kmax = int(steps.max()) if n > 0 else 0
            for k in range(kmax):
                idx = np.flatnonzero(steps > k)
                Y = X[:, idx]
                _fixed_step(Y, P, hseg, vseg)
                X[:, idx] = Y
            _apply_events(X, ev, P)
            _update(X, m, ev, dt, udt, P)
        phys[:, t, 0] = X[PX]
        phys[:, t, 1] = X[PY]
        rend[:, t, 0] = X[QX] + X[ALPHA] * (X[SX] - X[QX])
        rend[:, t, 1] = X[QY] + X[ALPHA] * (X[SY] - X[QY])
        vel[:, t, 0] = X[VX]
        vel[:, t, 1] = X[VY]
        modes[:, t] = X[MODE].astype(np.int32)
        flags[:, t] = _flags(X)
    return phys, rend, vel, modes, flags, X


@dataclass(slots=True)
class Rollout:
    """Rollout of N command sequences over T frames; index 0 is the start frame. With timing variants, the main
    arrays hold variant 0 (the nominal lane), bound the per-frame hull of every lane's box, flags_all / flags_any the
    per-frame AND / OR of their flags (F_INVULN in flags_all: invulnerable in every lane), and with lanes=True var_*
    hold every lane."""
    phys: np.ndarray     # [N, T+1, 2] body position, hero.pos coordinates (x centre, y = box bottom + foot)
    pos: np.ndarray      # [N, T+1, 2] rendered transform (STATE hero.pos; O-tagged pos_transform in WorldState)
    vel: np.ndarray      # [N, T+1, 2]
    mode: np.ndarray     # [N, T+1] M_* codes
    flags: np.ndarray    # [N, T+1] F_* bits
    final: np.ndarray    # [K, N] model state after the last frame
    box: np.ndarray      # [N, T+1, 4] collider AABB (x0, y0, x1, y1), as STATE hero.box
    variants: tuple = ()             # Variant per lane of the var_* arrays
    var_box: np.ndarray | None = None     # [N, V, T+1, 4]
    var_mode: np.ndarray | None = None    # [N, V, T+1]
    var_flags: np.ndarray | None = None   # [N, V, T+1]
    bound: np.ndarray | None = None       # [N, T+1, 4] hull of the variant boxes per frame
    flags_all: np.ndarray | None = None   # [N, T+1] F_* bits set in every lane
    flags_any: np.ndarray | None = None   # [N, T+1] F_* bits set in some lane

    @property
    def centre(self) -> np.ndarray:
        """[N, T+1, 2] collider centre: WorldState HeroState.pos (cross-module decision 1)."""
        return 0.5 * (self.box[..., :2] + self.box[..., 2:])


@dataclass(frozen=True, slots=True)
class Variant:
    """One timing lane. The game's timers compare float32 sums of frame times with thresholds that sit on exact
    multiples of 1/60 s (antic 0.1, hit-stop wait 0.1 and ramp 0.1, damage recoil 0.2, attack 0.35 ...), so the
    frame-time jitter (p99.99 0.0170 s against a mean of 0.016666 s) decides whether such a phase ends on frame N or
    N + 1, and the history cannot tell which (the frame times are not predictable: live run, 2.83 M frames). A lane
    moves the thresholds by -+ HeroParams.timer_bias, with its own sign for each link of the longest chain of such
    timers, the damage hit-stop wait, its ramp (GameManager.FreezeMoment, unscaled time) and every timer on scaled
    time (recoil, antic, recovery, attack, Bind): `timers` = (wait, ramp, scaled). alpha: the start phase ("est", or
    the "lo" / "hi" end of its feasible interval widened by HeroParams.alpha_margin); frame_time: unscaled frame
    time of every future frame ("mean", or the jitter model's "lo" / "hi", which also moves the physics phase);
    cast: the Silkspear throw / catch thresholds ("nominal", "short", "long", HeroParams.cast_variant)."""
    name: str
    alpha: str = "est"
    frame_time: str = "mean"
    cast: str = "nominal"
    timers: tuple = (0, 0, 0)


def _lane(t: tuple) -> Variant:
    early = t[2] < 0
    return Variant("".join("-+"[x > 0] for x in t), "hi" if early else "lo", "mean", "short" if early else "long", t)


_SIGNS = tuple((a, b, c) for a in (-1, 1) for b in (-1, 1) for c in (-1, 1))
NOMINAL = (Variant("nominal"),)
# fast: every threshold a frame sooner (later), the phase at the top (bottom) of its interval, short (long) Silkspear
FAST = (Variant("nominal"), _lane((-1, -1, -1)), _lane((1, 1, 1)))
# bounds: every combination of the three links, so a hit-stop that ends early and a recoil that ends late are covered
BOUNDS = (Variant("nominal"),) + tuple(_lane(t) for t in _SIGNS)
FULL = (Variant("nominal"),) + tuple(Variant(f"{a}/{_lane(t).name}", a, "mean", _lane(t).cast, t)
                                     for a in ("lo", "hi") for t in _SIGNS)
VARIANT_SETS = {"nominal": NOMINAL, "fast": FAST, "bounds": BOUNDS, "full": FULL}
_SCALED_TIMERS = ("P_ATK_DUR", "P_ATK_CD", "P_DS_ANTIC", "P_DS_REC", "P_DS_LREC", "P_HURT_T", "P_CAST_ANTIC",
                  "P_BIND_T")


def _variant_rows(params: HeroParams, variants: tuple[Variant, ...]
                  ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per variant: parameter row [V, NP], frame time [V] (0: the caller's), phase selector [V]."""
    V = len(variants)
    Pv = np.repeat(params.vector()[None, :], V, axis=0)
    ft = np.zeros(V)
    sel = np.zeros(V, dtype=np.int64)
    scaled = [globals()[k] for k in _SCALED_TIMERS]
    for v, var in enumerate(variants):
        sel[v] = {"est": 0, "lo": 1, "hi": 2}[var.alpha]
        ft[v] = {"mean": params.frame_time, "lo": params.frame_time_lo, "hi": params.frame_time_hi}[var.frame_time]
        Pv[v, P_CAST_THROW], Pv[v, P_CAST_CATCH], Pv[v, P_BIND_T] = params.cast_variant(var.cast)
        tw, tr, ts = var.timers
        Pv[v, P_HURT_WAIT] += tw * params.timer_bias
        Pv[v, P_HURT_RAMP] += tr * params.timer_bias
        Pv[v, P_WF_BW] += tw * params.timer_bias          # a world freeze's wait / ramp up: the same unscaled links
        Pv[v, P_WF_BU] += tr * params.timer_bias
        Pv[v, scaled] += ts * params.timer_bias
    return Pv, np.asarray(ft, dtype=np.float32).astype(np.float64), sel


def _lane_runs(P: np.ndarray, ft_v: np.ndarray, sel: np.ndarray, S0: np.ndarray, ev: np.ndarray, n: int
               ) -> np.ndarray:
    """[n, V] bool: which lanes a sequence has to run. Lanes that differ only in the unscaled-time links (hit-stop
    and world-freeze wait and ramp) give identical results for a sequence that meets neither (start mode not
    HURT_FREEZE, no world freeze running, no EV_HURT or EV_FZ_* event): of "bounds" (9 lanes) such a sequence
    runs 3."""
    V = len(ft_v)
    key = P.copy()
    key[:, [P_HURT_WAIT, P_HURT_RAMP, P_WF_BW, P_WF_BU]] = 0.0
    dup = np.zeros(V, dtype=bool)
    for v in range(1, V):
        dup[v] = any(not dup[w] and ft_v[w] == ft_v[v] and sel[w] == sel[v] and np.array_equal(key[w], key[v])
                     for w in range(v))
    run = np.ones((n, V), dtype=bool)
    if dup.any():
        hurt = np.broadcast_to((S0[MODE] == M_HURT_FREEZE) | (S0[WF_PH] >= 0), (n,)).copy()
        if ev.shape[0]:
            hurt |= ((ev & (EV_HURT_L | EV_HURT_R | EV_FZ_ANY)) != 0).any(axis=1)
        run[:, dup] = hurt[:, None]
    return run


def rollout(start: np.ndarray, masks: np.ndarray, params: HeroParams, terrain: Terrain2D | None = None,
            events: np.ndarray | None = None, dt: np.ndarray | None = None, fs: np.ndarray | None = None,
            udt: float | np.ndarray | None = None, variants: tuple[Variant, ...] | str | None = None,
            backend: str = "auto", threads: int = 1, lanes: bool = False) -> Rollout:
    """Predict N button sequences of T frames from a model state.

    start: [K] or [K, N] model state (estimate_state / initial_state); masks: [N, T] latched ACTION masks for the
    frames after the start frame (index 0 = next frame; hold_filter turns commanded masks into latched ones), applied
    as the oracle does (an ACTION for target frame F is latched for F, read by Update in F); events: [N, T] EV_*
    bits (None: none; at run time the threat layer supplies them or the planner branches on them); dt, fs: [T] or
    [N, T] logged scaled dt and physics steps per frame (replay only: the planner does not know them); without them
    the timing is nominal: dt = udt times the model's time scale, steps from the phase; udt: unscaled frame time, a
    scalar or [T] / [N, T] (None: params.frame_time, the measured mean frame time, not exactly 1/60 s).
    variants: "fast" / "bounds" / "full" / a tuple of Variant (nominal timing only): V lanes per sequence, their
    per-frame hull in `bound` and flag AND / OR in flags_all / flags_any; the main arrays hold the first (nominal)
    lane; lanes=True also returns every lane (var_*; the planner does not need them: without, the compiled path keeps
    no per-lane arrays and skips lanes that duplicate another, _lane_runs). backend: "numba" (the compiled loop,
    kin_jit), "numpy" (the reference), "auto"; threads > 1 runs the sequences in parallel (numba)."""
    masks = np.ascontiguousarray(masks, dtype=np.int64)
    if masks.ndim == 1:
        masks = masks[None, :]
    n, T = masks.shape
    S0 = np.asarray(start, dtype=np.float64)
    S0 = S0[:, None] if S0.ndim == 1 else S0
    if S0.shape[0] != K or S0.shape[1] not in (1, n):
        raise ValueError(f"start state {S0.shape}, expected ({K}, {n}) or ({K}, 1)")
    S0 = np.ascontiguousarray(S0)
    ev = np.zeros((0, 0), dtype=np.int64) if events is None else np.ascontiguousarray(
        np.broadcast_to(np.asarray(events, dtype=np.int64), (n, T)))
    if isinstance(variants, str):
        variants = VARIANT_SETS[variants]
    variants = tuple(variants) if variants else ()
    if variants and dt is not None:
        raise ValueError("timing variants need nominal timing (dt / fs None)")
    V = len(variants) or 1
    if variants:
        P, ft_v, sel = _variant_rows(params, variants)
    else:
        P, ft_v, sel = params.vector()[None, :], np.zeros(1), np.zeros(1, dtype=np.int64)
    u = np.asarray(params.frame_time if udt is None else udt, dtype=np.float32).astype(np.float64)
    udts = np.ascontiguousarray(u.reshape(1, 1) if u.ndim == 0 else (u[None, :] if u.ndim == 1 else u))
    if udts.shape[0] not in (1, n) or udts.shape[1] not in (1, T):
        raise ValueError(f"udt {udts.shape} does not broadcast to ({n}, {T})")
    if dt is not None:
        dts = np.ascontiguousarray(np.broadcast_to(np.asarray(dt, dtype=np.float64), (n, T)))
        fss = np.ascontiguousarray(np.broadcast_to(np.asarray(fs, dtype=np.float64), (n, T)))
    else:
        dts = fss = np.zeros((0, 0))
    terrain = terrain or Terrain2D.empty()
    use_jit = HAVE_NUMBA if backend == "auto" else backend == "numba"
    if variants and use_jit and not lanes:
        from ssbot.knowledge import kin_jit
        if threads > 1:
            import numba
            numba.set_num_threads(threads)
        run = _lane_runs(P, ft_v, sel, S0, ev, n)
        fn = kin_jit.simulate_bound_par if threads > 1 else kin_jit.simulate_bound
        phys, rend, vel, modes, flags, box, X, bound, f_all, f_any = fn(
            S0, masks, ev, dts, fss, udts, ft_v, sel, params.alpha_margin, P, terrain.packed(), run)
        return Rollout(phys, rend, vel, modes, flags, X, box, variants, bound=bound, flags_all=f_all,
                       flags_any=f_any)
    if use_jit:
        from ssbot.knowledge import kin_jit
        if threads > 1:
            import numba
            numba.set_num_threads(threads)
        fn = kin_jit.simulate_par if threads > 1 else kin_jit.simulate
        phys, rend, vel, modes, flags, box, X = fn(S0, masks, ev, dts, fss, udts, ft_v, sel, params.alpha_margin,
                                                   P, terrain.packed())
    else:
        phys, rend, vel, modes, flags, box, X = _simulate_lanes(S0, masks, ev, dts, fss, udts, ft_v, sel,
                                                                params.alpha_margin, P, terrain)
    if not variants:
        return Rollout(phys, rend, vel, modes, flags, X, box)
    vb = box.reshape(n, V, T + 1, 4)
    bound = np.concatenate([vb[..., :2].min(axis=1), vb[..., 2:].max(axis=1)], axis=-1)
    vf = flags.reshape(n, V, T + 1)
    sl = slice(0, None, V)
    return Rollout(phys[sl], rend[sl], vel[sl], modes[sl], flags[sl], X[:, sl], box[sl], variants,
                   vb, modes.reshape(n, V, T + 1), vf, bound, np.bitwise_and.reduce(vf, axis=1),
                   np.bitwise_or.reduce(vf, axis=1))


def _simulate_lanes(S0, masks, ev, dts, fss, udts, ft_v, sel, alpha_margin, P, terrain):
    """The NumPy reference: the broadcast inputs of kin_jit.simulate expanded to one column per lane (lane r * V + v),
    run per parameter row with _simulate."""
    n, T = masks.shape
    V = len(ft_v)
    nl = n * V
    lane_r = np.repeat(np.arange(n), V)
    lane_v = np.tile(np.arange(V), n)
    S = np.ascontiguousarray(np.broadcast_to(S0, (K, n))[:, lane_r])
    S[ALPHA] = np.where(sel[lane_v] == 1, np.maximum(S[ALO] - alpha_margin, 0.0),
                        np.where(sel[lane_v] == 2, S[AHI] + alpha_margin, S[ALPHA]))
    m = masks[lane_r]
    e = ev[lane_r] if ev.shape[0] else np.zeros((nl, T), dtype=np.int64)
    u = np.broadcast_to(udts, (n, T))[lane_r]
    u = np.where(ft_v[lane_v][:, None] > 0, ft_v[lane_v][:, None], u)
    d = dts[lane_r] if dts.shape[1] else np.zeros((nl, 0))
    f = fss[lane_r] if fss.shape[1] else np.zeros((nl, 0))
    out = [np.empty((nl, T + 1, 2)), np.empty((nl, T + 1, 2)), np.empty((nl, T + 1, 2)),
           np.empty((nl, T + 1), dtype=np.int32), np.empty((nl, T + 1), dtype=np.int32), np.empty((nl, T + 1, 4)),
           np.empty((K, nl))]
    hseg = np.ascontiguousarray(terrain.hseg, dtype=np.float64)
    vseg = np.ascontiguousarray(terrain.vseg, dtype=np.float64)
    for v in range(V):
        idx = np.flatnonzero(lane_v == v)
        pv = P[v] if P.shape[0] > 1 else P[0]
        res = _simulate(S[:, idx], m[idx], e[idx], d[idx], f[idx], u[idx], pv, hseg, vseg)
        for o, x in zip(out[:5], res[:5]):
            o[idx] = x
        ph = res[0]
        out[5][idx] = np.stack([ph[..., 0] - pv[P_HW], ph[..., 1] - pv[P_FOOT], ph[..., 0] + pv[P_HW],
                                ph[..., 1] + pv[P_HEAD]], axis=-1)
        out[6][:, idx] = res[5]
    return tuple(out)


# ---- the input path: oracle HoldFilter ------------------------------------------------------------------------

N_BUTTONS = 22
_LEFT_BIT, _RIGHT_BIT = 20, 21
_AGE_LONG = 1 << 20


@dataclass(slots=True)
class HoldState:
    """oracle/src/Input/HoldFilter.cs state per lane: the latched and wanted key sets, queued edges and latched age
    per key. (deferred / exclusiveWaiting only feed the filter's counters.) The planner keeps one in step with the
    ACTIONs it sends (hold_filter returns the next one) or rebuilds it from STATE act.hf."""
    latched: np.ndarray      # [n, 22] bool
    desired: np.ndarray      # [n, 22] bool
    pending: np.ndarray      # [n, 22] int
    age: np.ndarray          # [n, 22] int

    @classmethod
    def idle(cls, n: int = 1) -> "HoldState":
        """All keys up for a long time (an empty filter)."""
        z = np.zeros((n, N_BUTTONS), dtype=bool)
        return cls(z, z.copy(), np.zeros((n, N_BUTTONS), dtype=np.int64), np.full((n, N_BUTTONS), _AGE_LONG))

    @classmethod
    def from_hf(cls, hf: dict, n: int = 1) -> "HoldState":
        """From STATE act.hf {latched, desired, pending, age}: latched / desired as button masks (or per-key bool
        lists), pending / age as per-key lists (or {button index: value} maps; missing keys: 0 pending, long age)."""
        def bits(v) -> np.ndarray:
            if isinstance(v, (list, tuple)):
                a = np.zeros(N_BUTTONS, dtype=bool)
                a[:min(len(v), N_BUTTONS)] = np.asarray(v[:N_BUTTONS], dtype=bool)
                return a
            return ((int(v or 0) >> np.arange(N_BUTTONS)) & 1).astype(bool)

        def ints(v, default: int) -> np.ndarray:
            a = np.full(N_BUTTONS, default, dtype=np.int64)
            if isinstance(v, dict):
                for k, x in v.items():
                    if 0 <= int(k) < N_BUTTONS:
                        a[int(k)] = int(x)
            elif isinstance(v, (list, tuple)):
                m = min(len(v), N_BUTTONS)
                a[:m] = np.asarray(v[:m], dtype=np.int64)
            return a

        one = cls(bits(hf.get("latched"))[None], bits(hf.get("desired"))[None], ints(hf.get("pending"), 0)[None],
                  ints(hf.get("age"), _AGE_LONG)[None])
        return one.repeat(n)

    @classmethod
    def from_act(cls, act: dict | None, n: int = 1) -> "HoldState":
        """From a STATE "act" section: act.hf when the oracle exports it (exact), else the latched act.mask taken
        as settled (no queued edges, long ages), an approximation (oracle tests/InputLogicCheck, 1200 random cut
        points: 59 273 latched frames differ after it, 0 after act.hf), so a planner that sends the ACTIONs keeps
        its own HoldState in step instead (hold_filter returns it)."""
        act = act or {}
        hf = act.get("hf")
        if isinstance(hf, dict):
            return cls.from_hf(hf, n)
        m = int(act.get("mask") or 0)
        return cls.from_hf({"latched": m, "desired": m}, n)

    def repeat(self, n: int) -> "HoldState":
        return HoldState(*(np.repeat(a[:1] if len(a) == 1 else a, n if len(a) == 1 else 1, axis=0)
                           for a in (self.latched, self.desired, self.pending, self.age)))

    def copy(self) -> "HoldState":
        return HoldState(self.latched.copy(), self.desired.copy(), self.pending.copy(), self.age.copy())

    def mask(self) -> np.ndarray:
        """[n] latched button masks."""
        return (self.latched.astype(np.int64) << np.arange(N_BUTTONS, dtype=np.int64)).sum(axis=1)


def hold_filter(masks: np.ndarray, state: HoldState | None = None, min_press: int = 2, min_release: int = 2,
                max_pending: int = 3) -> tuple[np.ndarray, HoldState]:
    """(latched masks, filter state after the last frame) for commanded masks [N, T] (or [T]) fed to
    oracle/src/Input/HoldFilter.cs from `state` (None: idle; a one-lane state is shared by every lane). The filter
    (which the final SendInput sink enforces too) keeps every requested edge and replays it in order: a release
    waits until the key has been down min_press latched frames, a press until it has been up min_release frames,
    left and right are never latched together, and more than max_pending queued toggles of one key drop the oldest
    press + release pair. rollout() takes latched masks (logged "act" masks already are latched). ReleaseAll
    (input.release, harness operations) is not modelled."""
    masks = np.asarray(masks, dtype=np.int64)
    one = masks.ndim == 1
    masks = masks[None] if one else masks
    n, T = masks.shape
    st = (state or HoldState.idle(1)).copy()
    if len(st.latched) == 1 and n > 1:
        st = st.repeat(n)
    shift = np.arange(N_BUTTONS, dtype=np.int64)
    latched, desired, pending, age = st.latched, st.desired, st.pending, st.age
    out = np.zeros((n, T), dtype=np.int64)
    for t in range(T):
        want = ((masks[:, t:t + 1] >> shift) & 1).astype(bool)
        pending = pending + (want != desired)
        desired = want
        pending = np.where(pending > max_pending, pending - 2, pending)
        nxt = latched.copy()
        has = pending > 0
        rel = has & latched & (age >= min_press)
        prs = has & ~latched & (age >= min_release)
        nxt[rel] = False
        nxt[prs] = True
        pending = pending - (rel | prs)
        both = nxt[:, _LEFT_BIT] & nxt[:, _RIGHT_BIT]
        for b in (_LEFT_BIT, _RIGHT_BIT):
            rv = both & prs[:, b]
            nxt[rv, b] = False
            pending[rv, b] += 1
            stale = rv & ~desired[:, b]
            pending[stale, b] = 0
        toggled = nxt != latched
        age = np.where(toggled, 1, np.minimum(age + 1, _AGE_LONG))
        latched = nxt
        out[:, t] = (latched.astype(np.int64) << shift).sum(axis=1)
    new = HoldState(latched, desired, pending, age)
    return (out[0] if one else out), new


def initial_state(params: HeroParams, x: float, y: float, *, vx: float = 0.0, vy: float = 0.0, facing: int = 1,
                  ground: bool = True, silk: int = 0, alpha: float = 0.0, mode: int = M_NORMAL) -> np.ndarray:
    """A [K] state at rest (or with the given velocity): for tests, probes and planning from a known pose."""
    S = np.zeros(K)
    S[[PX, QX, SX]] = x
    S[[PY, QY, SY]] = y
    S[VX], S[VY] = vx, vy
    S[ALPHA] = S[ALO] = S[AHI] = alpha
    S[GS] = 1.0
    S[FACE] = 1.0 if facing >= 0 else -1.0
    S[GROUND] = 1.0 if ground else 0.0
    S[AIRHANG] = 0.0 if ground else 1.0
    S[MODE] = mode
    S[JQ] = S[AQ] = S[QQ] = -1.0
    S[DS_REC] = -1.0
    S[BOUNCE] = -1.0
    S[SILK] = silk
    S[JDSTEPS] = 100.0
    S[TS] = 1.0
    S[WF_PH] = -1.0
    S[WF_S] = 1.0
    return S


# ---- logged traces --------------------------------------------------------------------------------------------

CSTATE_NAMES_PATH = REPO / "docs" / "facts" / "1.0.30000" / "cstate_schema.json"
_CS_USED = ("facingRight", "onGround", "jumping", "attacking", "upAttacking", "downSpikeAntic", "downSpiking",
            "downSpikeBouncing", "downSpikeRecovery", "recoilingRight", "recoilingLeft", "recoilFrozen", "recoiling",
            "invulnerable", "casting", "isBinding", "isToolThrowing", "nailCharging", "hazardRespawning", "dead",
            "transitioning", "wallSliding", "dashing", "parrying")


MK_HARNESS, MK_HAZARD, MK_SCENE, MK_FREEZE, MK_DEATH, MK_SLIDE = 1, 2, 4, 8, 16, 32
# FreezeMoment starts per frame (oracle "freeze" events, Trace.freeze bits). Every StartRecoil comes with an
# EnemyDeath freeze in the same frame (live i0_000: 1974 / 1974), which ends inside the hit-stop and changes nothing;
# the others hold the time scale down while the hero model's clock runs on (MK_FREEZE).
FZ_RECOIL, FZ_ENEMY_DEATH, FZ_BIND_BREAK, FZ_BOSS_DEATH, FZ_BOSS_STUN, FZ_QUICK, FZ_OTHER = (1 << i for i in range(7))
_FZ_TYPES = {"EnemyDeath": FZ_ENEMY_DEATH, "BindBreak": FZ_BIND_BREAK, "BossDeathSlow": FZ_BOSS_DEATH,
             "BossStun": FZ_BOSS_STUN, "QuickFreeze": FZ_QUICK}
FZ_NAMES = {FZ_RECOIL: "StartRecoil", FZ_ENEMY_DEATH: "EnemyDeath", FZ_BIND_BREAK: "BindBreak",
            FZ_BOSS_DEATH: "BossDeathSlow", FZ_BOSS_STUN: "BossStun", FZ_QUICK: "QuickFreeze", FZ_OTHER: "other"}
# hero.tm (oracle STATE, when exported): HeroController timers, in this order as Trace.tm columns
TM_KEYS = ("inv", "recoil", "recoil_steps", "dash_cd", "atk_cd", "atk_t", "tool_cd", "jump_steps", "jumped_steps",
           "ds", "ds_rec", "grav", "qj", "qa", "qt")
SLIDE_SPAN = (-20, 40)  # rows around a savestate.load event searched for its slide (logged ~12 frames late)
_MARK_KINDS = {"harness": MK_HARNESS, "hazard_respawn": MK_HAZARD, "hazard_death": MK_HAZARD,
               "scene_enter": MK_SCENE, "scene_leave": MK_SCENE, "die": MK_DEATH, "hero_dead": MK_DEATH,
               "player_dead": MK_DEATH}


def cstate_names() -> list[str]:
    return json.loads(CSTATE_NAMES_PATH.read_text(encoding="utf-8"))["bools"]


@dataclass(slots=True)
class Trace:
    """Per-frame columns of a STATE stream, what the estimator, kin_fit and kin_check need (one row per frame)."""
    f: np.ndarray
    fs: np.ndarray
    dt: np.ndarray
    udt: np.ndarray
    ts: np.ndarray
    pos: np.ndarray        # [n, 2] rendered (hero.pos)
    phys: np.ndarray       # [n, 2] body, from hero.box
    vel: np.ndarray        # [n, 2]
    facing: np.ndarray
    hero_state: np.ndarray
    relinq: np.ndarray
    cs: np.ndarray         # [n, len(_CS_USED)] bool
    mask: np.ndarray       # buttons the game read in that frame
    silk: np.ndarray
    hp: np.ndarray
    clip: np.ndarray       # index into clips
    spell: np.ndarray      # index into spells
    dmg: np.ndarray        # damage taken this frame: -1 impact from the left, +1 from the right, 0 none
    marks: np.ndarray      # MK_* bits: frames whose motion the hero model cannot know (harness, hazard, scene)
    box: np.ndarray        # [n, 4] hero.box as logged
    valid: np.ndarray      # hero present, gameplay, not paused
    scene: np.ndarray      # index into scenes
    clips: list
    spells: list
    scenes: list
    mask_source: str = "act"
    tm: np.ndarray | None = None          # [n, len(TM_KEYS)] hero.tm when exported (NaN where missing)
    alpha_log: np.ndarray | None = None   # [n] hero.alpha when exported (NaN where missing)
    freeze: np.ndarray | None = None      # [n] FZ_* bits of the FreezeMoments started in that frame

    def __len__(self) -> int:
        return len(self.f)

    def flag(self, name: str) -> np.ndarray:
        return self.cs[:, _CS_USED.index(name)]

    def save(self, path: str | Path) -> None:
        d = {f.name: getattr(self, f.name) for f in fields(self) if getattr(self, f.name) is not None}
        meta = {k: d.pop(k) for k in ("clips", "spells", "scenes", "mask_source")}
        np.savez_compressed(path, meta=json.dumps(meta), **d)

    @classmethod
    def load(cls, path: str | Path) -> "Trace":
        z = np.load(path, allow_pickle=False)
        meta = json.loads(str(z["meta"]))
        return cls(**{k: z[k] for k in z.files if k != "meta"}, **meta)

    def row(self, i: int) -> dict:
        """Row i in StateTracker.push_row terms (replaying a recording through the live path)."""
        return {"f": int(self.f[i]), "fs": int(self.fs[i]), "dt": float(self.dt[i]), "udt": float(self.udt[i]),
                "ts": float(self.ts[i]), "phys": self.phys[i], "vel": self.vel[i], "box": self.box[i],
                "facing": int(self.facing[i]), "hero_state": int(self.hero_state[i]), "relinq": bool(self.relinq[i]),
                "cs": self.cs[i], "mask": int(self.mask[i]), "silk": int(self.silk[i]),
                "clip": self.clips[self.clip[i]], "spell": self.spells[self.spell[i]], "dmg": int(self.dmg[i]),
                "marks": int(self.marks[i]), "freeze": int(self.freeze[i]) if self.freeze is not None else 0,
                "valid": bool(self.valid[i]),
                "tm": self.tm[i] if self.tm is not None else np.full(len(TM_KEYS), np.nan),
                "alpha": float(self.alpha_log[i]) if self.alpha_log is not None else np.nan,
                "load": bool(self.marks[i] & MK_SLIDE)}

    def slice(self, i0: int, i1: int) -> "Trace":
        d = {}
        for f in fields(self):
            v = getattr(self, f.name)
            d[f.name] = v[i0:i1] if isinstance(v, np.ndarray) else v
        return Trace(**d)

    @classmethod
    def from_states(cls, states: Iterable[dict], params: HeroParams | None = None, mask_source: str = "auto",
                    names: list[str] | None = None) -> "Trace":
        """From STATE dicts (RecordingReader.states, raw_session.states, OracleLink). mask_source "act" (the
        injected ACTION, exact) or "input" (what the game's action layer saw; the jump bit is moved back by
        params.input_jump_lag frames); "auto": act when any frame has a nonzero act mask."""
        params = params or HeroParams()
        names = names or cstate_names()
        bit = [names.index(n) for n in _CS_USED]
        clips: dict = {}
        spells: dict = {}
        scenes: dict = {}
        cols: dict[str, list] = {k: [] for k in ("f", "fs", "dt", "udt", "ts", "pos", "phys", "vel", "facing",
                                                 "hero_state", "relinq", "cs", "act", "inp", "silk", "hp", "clip",
                                                 "spell", "dmg", "marks", "box", "valid", "scene", "freeze")}
        nan2 = [np.nan, np.nan]
        nan_tm = [np.nan] * len(TM_KEYS)
        tm_rows: list = []
        alpha_rows: list = []
        loads: list = []
        for s in states:
            h = s.get("hero")
            g = s.get("game") or {}
            tm = (h or {}).get("tm")
            tm_rows.append([float(tm[k]) if isinstance(tm, dict) and tm.get(k) is not None else np.nan
                            for k in TM_KEYS] if tm else nan_tm)
            a = (h or {}).get("alpha")
            alpha_rows.append(float(a) if a is not None else np.nan)
            if any(e.get("k") == "harness" and (e.get("d") or {}).get("op") == "savestate.load"
                   for e in s.get("ev") or ()):
                loads.append(len(cols["f"]))
            cols["f"].append(s["f"])
            cols["fs"].append(s.get("fs") or 0)
            cols["dt"].append(s.get("dt") or 0.0)
            cols["udt"].append(s.get("udt") or 0.0)
            cols["ts"].append(s.get("ts", 1.0) if s.get("ts") is not None else 1.0)
            cols["act"].append((s.get("act") or {}).get("mask", 0) or 0)
            cols["inp"].append((s.get("input") or {}).get("mask", 0) or 0)
            cols["scene"].append(scenes.setdefault(g.get("scene"), len(scenes)))
            dmg = 0
            mk = 0
            fz = 0
            for ev in s.get("ev") or ():
                k = ev.get("k")
                d = ev.get("d") or {}
                if k == "damage":
                    side = d.get("side")
                    dmg = -1 if side == "left" else 1 if side == "right" else dmg
                elif k == "freeze" and d.get("phase") == "start":
                    typ = str(d.get("type"))
                    fz |= FZ_RECOIL if "StartRecoil" in typ else _FZ_TYPES.get(typ, FZ_OTHER)
                else:
                    mk |= _MARK_KINDS.get(k, 0)
            if fz & ~(FZ_RECOIL | FZ_ENEMY_DEATH) or (fz & FZ_ENEMY_DEATH and not fz & FZ_RECOIL):
                mk |= MK_FREEZE
            cols["dmg"].append(dmg)
            cols["marks"].append(mk)
            cols["freeze"].append(fz)
            if not h or not h.get("box") or not h.get("cstate"):
                for k, v in (("pos", nan2), ("phys", nan2), ("vel", nan2), ("box", nan2 * 2), ("facing", 0),
                             ("hero_state", -1), ("relinq", False), ("cs", [False] * len(bit)), ("silk", 0), ("hp", 0),
                             ("valid", False)):
                    cols[k].append(v)
                cols["clip"].append(clips.setdefault(None, len(clips)))
                cols["spell"].append(spells.setdefault(None, len(spells)))
                continue
            b = h["box"]
            words = h["cstate"]
            cols["pos"].append(h["pos"][:2])
            cols["phys"].append([0.5 * (b[0] + b[2]), b[1] + params.foot])
            cols["box"].append(b[:4])
            cols["vel"].append(h.get("vel") or [0.0, 0.0])
            cols["facing"].append(h.get("facing", 1))
            cols["hero_state"].append(h.get("hero_state", -1))
            cols["relinq"].append(bool(h.get("control_relinquished")))
            cols["cs"].append([bool((words[i >> 6] >> (i & 63)) & 1) for i in bit])
            cols["silk"].append(h.get("silk") or 0)
            cols["hp"].append(h.get("health") or 0)
            cols["clip"].append(clips.setdefault((h.get("anim") or {}).get("clip"), len(clips)))
            cols["spell"].append(spells.setdefault((h.get("spell") or [None])[0], len(spells)))
            pause = s.get("pause") or {}
            cols["valid"].append(g.get("gs", 4) == 4 and not g.get("paused") and not pause.get("inv", False))
        act = np.asarray(cols.pop("act"), dtype=np.int64)
        inp = np.asarray(cols.pop("inp"), dtype=np.int64)
        if mask_source == "auto":
            mask_source = "act" if act.any() else "input"
        if mask_source == "act":
            mask = act
        else:
            mask = inp.copy()
            lag = int(params.input_jump_lag)
            if lag > 0 and len(mask) > lag:
                # only the press shows late (bot runs: act vs input; the release is on the same frame), so the
                # jump is held from the shifted press to the logged release
                j = inp & B_JUMP
                mask = (mask & ~B_JUMP) | j | np.concatenate([j[lag:], np.zeros(lag, dtype=np.int64)])
        arr = {k: np.asarray(v) for k, v in cols.items()}
        tm_arr = np.asarray(tm_rows, dtype=np.float64).reshape(-1, len(TM_KEYS))
        al = np.asarray(alpha_rows, dtype=np.float64)
        tr = cls(f=arr["f"].astype(np.int64), fs=arr["fs"].astype(np.int64), dt=arr["dt"].astype(np.float64),
                 udt=arr["udt"].astype(np.float64), ts=arr["ts"].astype(np.float64),
                 pos=arr["pos"].astype(np.float64).reshape(-1, 2), phys=arr["phys"].astype(np.float64).reshape(-1, 2),
                 vel=arr["vel"].astype(np.float64).reshape(-1, 2), facing=arr["facing"].astype(np.int8),
                 hero_state=arr["hero_state"].astype(np.int16), relinq=arr["relinq"].astype(bool),
                 cs=arr["cs"].astype(bool).reshape(-1, len(_CS_USED)), mask=mask, silk=arr["silk"].astype(np.int16),
                 hp=arr["hp"].astype(np.int16), clip=arr["clip"].astype(np.int32),
                 spell=arr["spell"].astype(np.int32), dmg=arr["dmg"].astype(np.int8),
                 marks=arr["marks"].astype(np.int16), box=arr["box"].astype(np.float64).reshape(-1, 4),
                 valid=arr["valid"].astype(bool),
                 scene=arr["scene"].astype(np.int32), clips=list(clips), spells=list(spells), scenes=list(scenes),
                 mask_source=mask_source, tm=tm_arr if np.isfinite(tm_arr).any() else None,
                 alpha_log=al if np.isfinite(al).any() else None, freeze=arr["freeze"].astype(np.int16))
        mark_load_slides(tr, loads, params)
        return tr


def mark_load_slides(tr: Trace, loads: Iterable[int], params: HeroParams) -> int:
    """MK_SLIDE on the frames where a savestate load is still moving the hero back to the saved position: the box
    moves with velocity 0 and no physics step (2026-10-01, trial run f 56185-56193: 0.60 u per frame towards x 78,
    for up to 17 frames around the 'savestate.load' harness event; ssbot.train.episode.wait_settled). Searched in
    SLIDE_SPAN around each load row; the frames between the first and the last such motion are marked. Returns the
    number of frames marked."""
    n = len(tr)
    if n < 2:
        return 0
    d = np.abs(np.diff(tr.box[:, :2], axis=0))
    v = np.maximum(np.abs(tr.vel[1:]), np.abs(tr.vel[:-1]))
    allowed = v * (np.maximum(tr.fs[1:], 0)[:, None] * params.fdt) + 0.05
    bad = np.r_[False, ((d > allowed) & np.isfinite(d)).any(axis=1)]
    marked = 0
    for i in loads:
        lo, hi = max(i + SLIDE_SPAN[0], 0), min(i + SLIDE_SPAN[1], n)
        idx = np.flatnonzero(bad[lo:hi]) + lo
        if len(idx):
            sel = slice(idx[0], idx[-1] + 1)
            marked += int(np.sum((tr.marks[sel] & MK_SLIDE) == 0))
            tr.marks[sel] |= MK_SLIDE
    return marked


# ---- state estimation from a trace ----------------------------------------------------------------------------

HS_NO_INPUT = 7       # GlobalEnums.ActorStates.no_input
CAST_CLIPS = ("NeedleThrow AnticG", "NeedleThrow AnticA", "NeedleThrow Throwing", "NeedleThrow Catch",
              "NeedleThrow Burst")
BIND_SPELLS = ("Binding", "Bind Air", "Bind Ground", "Bind Burst", "BindCharge", "Bind Start")


def _onset(x: np.ndarray) -> np.ndarray:
    x = x.astype(bool)
    return x & ~np.r_[False, x[:-1]]


def _since(onset: np.ndarray, per_frame: np.ndarray, include_onset: bool) -> np.ndarray:
    """Running sum of per_frame since the last onset (inclusive or exclusive of the onset frame's own value)."""
    c = np.cumsum(per_frame)
    idx = np.where(onset, np.arange(len(onset)), -1)
    last = np.maximum.accumulate(idx)
    base = np.where(last >= 0, c[np.maximum(last, 0)] - (per_frame[np.maximum(last, 0)] if include_onset else 0), 0)
    out = c - base
    return np.where(last >= 0, out, np.inf)


def _since32(onset: np.ndarray, per_frame: np.ndarray, include_onset: bool) -> np.ndarray:
    """_since with the game's float32 accumulation (timers compared against thresholds must match it bit for bit)."""
    out = np.full(len(onset), np.inf)
    acc = None
    pf = per_frame.astype(np.float32)
    for i in range(len(onset)):
        if onset[i]:
            acc = pf[i] if include_onset else np.float32(0.0)
        elif acc is not None:
            acc = np.float32(acc + pf[i])
        if acc is not None:
            out[i] = float(acc)
    return out


def _freeze_replay(tr: Trace, params: HeroParams) -> np.ndarray:
    """[n, 4] (phase, timer, frames since the hit, time scale) of the hit-stop emulation (see _update), replayed from
    each logged damage frame with the logged unscaled frame times."""
    out = np.zeros((len(tr), 4))
    out[:, 3] = 1.0
    udt = tr.udt.astype(np.float32)
    for i0 in np.flatnonzero(_onset(tr.flag("recoilFrozen"))):
        ph, t, ts = 0, np.float32(0), 0.0
        for k in range(0, 40):
            i = i0 + k
            if i >= len(tr):
                break
            if ph == 0 and k >= params.hurt_wait_skip + 1:
                t = np.float32(t + udt[i])
                if t >= np.float32(params.hurt_wait):
                    ph, t = 1, np.float32(0)
                    out[i] = (ph, t, k + 1, ts)
                    continue
            elif ph == 1:
                t = np.float32(t + udt[i])
                ts = min(float(t) / params.hurt_ramp, 1.0)
                if t >= np.float32(params.hurt_ramp):
                    out[i] = (2, 0.0, k + 1, 1.0)
                    break
            out[i] = (ph, float(t), k + 1, ts)
    return out


def _wf_row(st: np.ndarray, start_bits: int, udt: float, P: np.ndarray) -> np.ndarray:
    """One frame of the world-freeze rows (WF_PH .. WF_TGT as a [7] array, after the frame's Update) for the
    estimator and the tracker: the model's own _wf_start / _wf_step on one lane."""
    X = np.zeros((K, 1))
    X[WF_PH:WF_TGT + 1, 0] = st
    for bit in WF_ORDER:
        if start_bits & bit:
            _wf_start(X, np.array([True]), FREEZE_PRESETS[bit])
    _wf_step(X, np.array([udt]), P)
    return X[WF_PH:WF_TGT + 1, 0].copy() if X[WF_PH, 0] >= 0 else WF_IDLE.copy()


WF_IDLE = np.array([-1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0])     # WF_PH .. WF_TGT of no world freeze


def _wf_replay(tr: Trace, modes: np.ndarray, params: HeroParams) -> np.ndarray:
    """[n, 7] world-freeze rows per logged frame, replayed from the logged FreezeMoment starts (BindBreak from a
    hit during the Bind charge, as the model starts it) with the logged unscaled frame times."""
    n = len(tr)
    out = np.repeat(WF_IDLE[None], n, axis=0)
    if n == 0:
        return out
    starts = _freeze_events(tr.freeze.astype(np.int64)) if tr.freeze is not None else np.zeros(n, dtype=np.int64)
    hit = _onset(tr.flag("recoilFrozen"))
    P = params.vector()
    st = WF_IDLE.copy()
    mode_t = None
    for i in range(n):
        bits = int(starts[i])
        if hit[i] and i > 0 and modes[i - 1] == M_BIND:
            if mode_t is None:
                mode_t = _bind_time(tr, modes)
            if mode_t[i - 1] < params.bind_break_before:
                bits |= EV_FZ_BIND_BREAK
        if bits == 0 and st[0] < 0:
            continue
        st = _wf_row(st, bits, float(tr.udt[i]), P)
        out[i] = st
    return out


def _bind_time(tr: Trace, modes: np.ndarray) -> np.ndarray:
    """Scaled s in Bind at each row (the model's MODE_T in BIND: float32 dt summed from the frame after entry)."""
    m_on = np.r_[True, modes[1:] != modes[:-1]]
    return _since32(m_on, tr.dt, include_onset=False)


def classify_modes(tr: Trace) -> np.ndarray:
    """Model mode per logged frame (M_*), from cstate, hero_state and the animation."""
    n = len(tr)
    mode = np.full(n, M_NORMAL, dtype=np.int8)
    clip = np.array(tr.clips, dtype=object)[tr.clip]
    spell = np.array(tr.spells, dtype=object)[tr.spell]
    cast = np.isin(clip, CAST_CLIPS)
    bind = tr.flag("isBinding") | np.isin(spell, BIND_SPELLS)
    mode[tr.relinq] = M_LOCKED
    mode[cast & (tr.relinq | (tr.hero_state == HS_NO_INPUT))] = M_CAST
    mode[bind & (tr.relinq | (tr.hero_state == HS_NO_INPUT))] = M_BIND
    mode[tr.flag("downSpikeAntic")] = M_DS_ANTIC
    mode[tr.flag("downSpiking")] = M_DS_SPIKE
    mode[tr.flag("recoiling") & (tr.hero_state == HS_NO_INPUT)] = M_HURT_RECOIL
    mode[tr.flag("recoilFrozen")] = M_HURT_FREEZE
    return mode


def derive_events(tr: Trace, modes: np.ndarray | None = None) -> np.ndarray:
    """Contact events of the logged frames (EV_* bits), for replaying play through the model."""
    modes = classify_modes(tr) if modes is None else modes
    ev = np.zeros(len(tr), dtype=np.int64)
    ev[_onset(tr.flag("recoilingLeft"))] |= EV_RECOIL_L
    ev[_onset(tr.flag("recoilingRight"))] |= EV_RECOIL_R
    ev[_onset(tr.flag("downSpikeBouncing"))] |= EV_POGO
    clip = np.array(tr.clips, dtype=object)[tr.clip]
    ev[_onset(clip == "NeedleThrow Catch") & (modes == M_CAST)] |= EV_CATCH
    ev[np.r_[False, tr.silk[1:] > tr.silk[:-1]]] |= EV_SILK     # silk from nail hits (bind / cast legality)
    # an up slash that connects stops the rise (RecoilDown): vy from > 0 to exactly 0 in the air, no landing
    vy, vy0 = tr.vel[:, 1], np.r_[0.0, tr.vel[:-1, 1]]
    ground = tr.flag("onGround")
    rising = (vy0 > 0) | (np.r_[False, tr.flag("jumping")[:-1]] & (tr.fs > 0))   # a jump's first step counts too
    ev[(vy == 0) & rising & ~ground & (modes == M_NORMAL) & np.r_[False, modes[:-1] == M_NORMAL] &
       (tr.flag("attacking") | tr.flag("upAttacking"))] |= EV_RECOIL_DOWN
    # StartRecoil sets recoilFrozen: a "damage" event without it (i-frame and bind paths deeper in TakeDamage) moves
    # nothing; the hero turns to face the impact side
    hit = _onset(tr.flag("recoilFrozen"))
    side = np.where(tr.dmg != 0, tr.dmg, np.where(tr.facing >= 0, 1, -1))
    ev[hit & (side < 0)] |= EV_HURT_L
    ev[hit & (side > 0)] |= EV_HURT_R
    locked = modes == M_LOCKED
    ev[_onset(locked)] |= EV_LOCK
    ev[_onset(~locked) & np.r_[False, locked[:-1]]] |= EV_UNLOCK
    if tr.freeze is not None:
        ev |= _freeze_events(tr.freeze.astype(np.int64))
    return ev


def _freeze_events(fz):
    """EV_FZ_* bits from the logged FreezeMoment starts (Trace.freeze): the world freezes the threat layer has to
    announce; EnemyDeath only without a hit in the same frame (with one it ends inside the hit-stop), BindBreak
    never (the model starts it from the hit during the Bind charge)."""
    ev = np.where((fz & FZ_BOSS_DEATH) != 0, EV_FZ_BOSS_DEATH, 0) | np.where((fz & FZ_BOSS_STUN) != 0,
                                                                             EV_FZ_BOSS_STUN, 0)
    ev |= np.where((fz & FZ_QUICK) != 0, EV_FZ_QUICK, 0)
    ev |= np.where(((fz & FZ_ENEMY_DEATH) != 0) & ((fz & FZ_RECOIL) == 0), EV_FZ_ENEMY_DEATH, 0)
    return ev


def estimate_state(tr: Trace, idx: Iterable[int] | np.ndarray, params: HeroParams,
                   modes: np.ndarray | None = None, alpha: np.ndarray | None = None,
                   terrain: Terrain2D | None = None, table: np.ndarray | None = None,
                   causal: bool = True) -> np.ndarray:
    """Model state [K, len(idx)] at the end of the given trace rows, from the logged pose, velocity and cstate, with
    the hidden timers (jump steps, attack time, recoil steps, mode time) counted from the flags' onsets. Every row
    uses only the frames up to it (the planner's information set; causal=False takes the physics phase from the
    whole trace, for replays). `table` (state_table of the same trace) saves recomputing the per-frame columns when
    many rows are estimated. hero.tm / hero.alpha replace the reconstructed timers and phase where exported."""
    idx = np.asarray(list(idx) if not isinstance(idx, np.ndarray) else idx, dtype=np.int64)
    table = state_table(tr, params, modes, alpha, causal) if table is None else table
    S = table[:, idx].copy()
    if terrain is not None:     # falling body parked on a floor without contact yet (see _move_y)
        near = _on_ground(S[PX], S[PY], params.vector(), terrain.hseg)
        S[TOUCH] = (near & (S[GROUND] <= 0) & (S[VY] < 0)).astype(np.float64)
    return S


def state_table(tr: Trace, params: HeroParams, modes: np.ndarray | None = None,
                alpha: np.ndarray | None = None, causal: bool = True) -> np.ndarray:
    """Model state [K, len(tr)] at the end of every trace row (terrain contact left out, see estimate_state). Each
    row depends on that row and the ones before it only (with causal=False the phase uses the whole trace)."""
    n = len(tr)
    idx = np.arange(n)
    modes = classify_modes(tr) if modes is None else modes
    if alpha is None:
        alpha, a_lo, a_hi = phase_interval(tr, params.fdt, causal=causal)
    else:
        a_lo = a_hi = alpha
    steps = tr.fs.astype(np.float64)
    dt = tr.dt
    S = np.zeros((K, len(idx)))
    S[PX], S[PY] = tr.phys[idx, 0], tr.phys[idx, 1]
    # interpolation endpoints: the step pose is the box at the frame's end unless an Update moved the body since
    S[SX], S[SY] = S[PX], S[PY]
    last_step = np.where(steps > 0, np.arange(n), -1)
    last_step = np.maximum.accumulate(last_step)
    before = np.maximum(last_step[idx] - 1, 0)
    q = tr.phys[before]
    S[QX], S[QY] = q[:, 0], q[:, 1]
    S[VX], S[VY] = tr.vel[idx, 0], tr.vel[idx, 1]
    S[ALPHA] = alpha[idx]
    S[ALO], S[AHI] = a_lo[idx], a_hi[idx]
    S[FACE] = np.where(tr.facing[idx] >= 0, 1.0, -1.0)
    ground = tr.flag("onGround")
    S[GROUND] = ground[idx]
    S[MODE] = modes[idx]
    S[SILK] = tr.silk[idx]
    S[PREV] = tr.mask[idx]
    S[MOVE] = (np.where((tr.mask[idx] & B_RIGHT) != 0, 1.0, 0.0) - np.where((tr.mask[idx] & B_LEFT) != 0, 1.0, 0.0))
    S[JHELD] = (tr.mask[idx] & B_JUMP) != 0

    # jumps: steps since the onset of cState.jumping (a pogo starts at 4 / -20)
    jumping = tr.flag("jumping")
    j_on = _onset(jumping)
    pogo_on = _onset(tr.flag("downSpikeBouncing"))
    since_j = _since(j_on, steps, include_onset=False)
    pogo_j = _since(j_on, pogo_on.astype(np.float64), include_onset=True) > 0
    S[JUMPING] = jumping[idx]
    S[JSTEPS] = np.where(jumping[idx], np.where(pogo_j[idx], params.pogo_jump_steps, 0) + since_j[idx], 0)
    jd = np.where(pogo_j, params.pogo_jumped_steps, 0) + since_j
    S[JDSTEPS] = np.where(np.isfinite(jd[idx]), jd[idx], 100.0)
    att = tr.flag("attacking")
    a_on = _onset(att)
    ds_on = _onset(tr.flag("downSpikeAntic"))
    # input queues: a press that started nothing counts steps while the button stays down and nothing starts
    prev_mask = np.r_[0, tr.mask[:-1]]
    ar = np.arange(n)
    c_on = _onset(np.isin(modes, (M_CAST, M_BIND)))
    for row, bit, started in ((JQ, B_JUMP, j_on), (AQ, B_ATTACK, a_on | ds_on), (QQ, B_QUICKCAST, c_on)):
        held = (tr.mask & bit) != 0
        q_on = held & ((prev_mask & bit) == 0) & ~started
        last_q = np.maximum.accumulate(np.where(q_on, ar, -1))
        last_kill = np.maximum.accumulate(np.where(~held | started, ar, -1))
        alive = (last_q >= 0) & (last_q > last_kill)
        since_q = _since(q_on, steps, include_onset=False)
        S[row] = np.where(alive[idx], since_q[idx], -1.0)
    # gravity scale and air hang, replayed over the log with the FixedUpdate rules
    gs, hang = _replay_gravity(tr, modes, params)
    S[GS], S[AIRHANG] = gs[idx], hang[idx]
    # attacks (float32 timers, as the game keeps them)
    S[ATTACKING] = att[idx]
    S[ATK_T] = np.where(att[idx], _since32(a_on, dt, include_onset=False)[idx], 0.0)
    cd = np.float32(params.attack_cooldown) - _since32(a_on | ds_on, dt, include_onset=True)
    S[ATK_CD] = np.where(np.isfinite(cd[idx]), np.maximum(cd[idx], 0.0), 0.0)
    # nail recoil
    rl, rr = tr.flag("recoilingLeft"), tr.flag("recoilingRight")
    r_on = _onset(rl) | _onset(rr)
    S[RDIR] = np.where(rl[idx], -1.0, np.where(rr[idx], 1.0, 0.0))
    S[RSTEPS] = np.where(S[RDIR] != 0, np.maximum(params.recoil_steps - _since(r_on, steps, False)[idx], 0.0), 0.0)
    # downspike
    face_at = np.where(tr.facing >= 0, 1.0, -1.0)
    last_ds = np.maximum.accumulate(np.where(ds_on, np.arange(n), -1))
    S[DS_HS] = np.where(last_ds[idx] >= 0, face_at[np.maximum(last_ds[idx], 0)] * params.ds_speed, 0.0)
    rec = tr.flag("downSpikeRecovery")
    S[DS_REC] = np.where(rec[idx], _since32(_onset(rec), dt, include_onset=True)[idx], -1.0)
    bnc = tr.flag("downSpikeBouncing")
    S[BOUNCE] = np.where(bnc[idx], _since(_onset(bnc), steps, include_onset=False)[idx], -1.0)
    # time in mode: inclusive of the entry frame where the game's timer starts there (antic), else exclusive
    m_on = np.r_[True, modes[1:] != modes[:-1]]
    md = modes[idx]
    t_in = _since32(m_on, dt, include_onset=True)[idx]
    t_after = _since32(m_on, dt, include_onset=False)[idx]
    st_after = _since32(m_on, steps * np.float32(params.fdt), include_onset=False)[idx]
    mt = np.where(md == M_DS_SPIKE, st_after, np.where(md == M_DS_ANTIC, t_in, t_after))
    S[MODE_T] = np.where(np.isfinite(mt), mt, 0.0)
    S[MODE_N] = np.where(np.isfinite(t_after), _since(m_on, np.ones(n), include_onset=False)[idx], 0.0)
    S[TS] = tr.ts[idx]
    # hit-stop: replay the FreezeMoment emulation from the damage frame
    fz = _freeze_replay(tr, params)[idx]
    frz = md == M_HURT_FREEZE
    S[PHASE] = np.where(frz, np.minimum(fz[:, 0], 1.0), S[PHASE])
    S[MODE_T] = np.where(frz, fz[:, 1], S[MODE_T])
    S[MODE_N] = np.where(frz, fz[:, 2], S[MODE_N])
    dmg_on = _onset(tr.flag("recoilFrozen"))
    side = np.where(tr.dmg != 0, tr.dmg, np.where(tr.facing >= 0, 1, -1)).astype(np.float64)
    last_d = np.maximum.accumulate(np.where(dmg_on, np.arange(n), -1))
    sd = np.where(last_d[idx] >= 0, side[np.maximum(last_d[idx], 0)], 0.0)
    S[HVX] = -sd * params.hurt_velocity
    S[HVY] = params.hurt_velocity * params.hurt_vy_ratio
    # Silkspear phase from the animation, its timer from the phase's first frame (exclusive)
    clip_all = np.array(tr.clips, dtype=object)[tr.clip]
    cph_all = np.where(clip_all == "NeedleThrow Throwing", 1.0, np.where(clip_all == "NeedleThrow Catch", 2.0, 0.0))
    cast_all = modes == M_CAST
    p_on = cast_all & (~np.r_[False, cast_all[:-1]] | (cph_all != np.r_[0.0, cph_all[:-1]]))
    pt = _since32(p_on, dt, include_onset=False)[idx]
    S[PHASE] = np.where(md == M_CAST, cph_all[idx], S[PHASE])
    S[MODE_T] = np.where((md == M_CAST) & np.isfinite(pt), pt, S[MODE_T])
    inv = tr.flag("invulnerable")
    left = np.float32(params.invul_time) - _since32(_onset(inv), dt, include_onset=False)
    S[INV_T] = np.where(inv[idx] & np.isfinite(left[idx]), np.maximum(left[idx], 0.0), 0.0)
    S[LEDGE] = 0.0
    # world freezes: their rows, and the hero's own part of the time scale where one runs (the logged ts is the
    # product of both)
    wf = _wf_replay(tr, modes, params)[idx]
    S[WF_PH:WF_TGT + 1] = wf.T
    act = wf[:, 0] >= 0
    S[TS] = np.where(act, np.where(frz, fz[:, 3], 1.0), S[TS])
    _apply_exported(tr, S, md, params)
    return S


def _apply_exported(tr: Trace, S: np.ndarray, md: np.ndarray, params: HeroParams) -> None:
    """Replace reconstructed rows by the oracle's own values where STATE carries them (hero.tm, hero.alpha;
    cross-module decision 5). Reconstruction errors they remove: the phase interval (the alpha lanes collapse to
    one), gravity scale after air hang, the queue step counters (a press queued before the window), nail and damage
    recoil left, attack and downspike timers when a flag onset was missed (pause, scene load, first frame)."""
    if tr.alpha_log is not None:
        a = tr.alpha_log
        ok = np.isfinite(a)
        for r in (ALPHA, ALO, AHI):
            S[r] = np.where(ok, a, S[r])
    if tr.tm is None:
        return
    col = {k: tr.tm[:, i] for i, k in enumerate(TM_KEYS)}

    def put(row: int, v: np.ndarray, where: np.ndarray | bool = True) -> None:
        S[row] = np.where(np.isfinite(v) & where, v, S[row])

    put(INV_T, np.maximum(col["inv"], 0.0))
    put(MODE_T, params.hurt_recoil_time - col["recoil"], md == M_HURT_RECOIL)
    put(RSTEPS, col["recoil_steps"], S[RDIR] != 0)
    put(ATK_CD, np.maximum(col["atk_cd"], 0.0))
    put(ATK_T, col["atk_t"], S[ATTACKING] > 0)
    put(JSTEPS, col["jump_steps"], S[JUMPING] > 0)
    put(JDSTEPS, col["jumped_steps"])
    put(MODE_T, col["ds"], (md == M_DS_ANTIC) | (md == M_DS_SPIKE))
    put(DS_REC, col["ds_rec"], S[DS_REC] >= 0)
    put(GS, col["grav"])
    # queue counters: the oracle exports the raw jumpQueueSteps / attackQueueSteps / toolThrowQueueSteps (>= 0;
    # docs/facts/1.0.30000/state_fields_m2.md section 1), not the jumpQueuing / attackQueuing / toolThrowQueueing
    # flags: a release clears the flag and leaves the count (HeroController.cs 8427-8450), so a count alone does not
    # say the queue is on. It replaces the reconstructed count where the reconstruction has the queue on, or where it
    # grew in this frame's physics steps with the button still held (FixedUpdate counts only while queuing, 3203-3226:
    # a press queued before the history starts)
    for row, k, bit in ((JQ, "qj", B_JUMP), (AQ, "qa", B_ATTACK), (QQ, "qt", B_QUICKCAST)):
        v = col[k]
        before = np.r_[np.nan, v[:-1]]
        with np.errstate(invalid="ignore"):
            grew = np.isfinite(before) & (v > before) & ((tr.mask & bit) != 0)
        on = np.isfinite(v) & ((S[row] >= 0) | grew)
        S[row] = np.where(on, np.maximum(v, 0.0), S[row])


def _replay_gravity(tr: Trace, modes: np.ndarray, params: HeroParams) -> tuple[np.ndarray, np.ndarray]:
    """gravityScale and didAirHang per logged frame (not exported), by running the FixedUpdate air-hang rules over
    the logged velocity, ground flag, jump button and mode."""
    n = len(tr)
    gs = np.ones(n)
    hang = np.zeros(n)
    g, h = 1.0, 0.0
    ground = tr.flag("onGround")
    jheld = (tr.mask & B_JUMP) != 0
    relinq_modes = np.isin(modes, RELINQUISHED)
    noinp = np.isin(modes, NO_INPUT)
    catch = np.array(tr.clips, dtype=object)[tr.clip] == "NeedleThrow Catch"
    for i in range(n):
        m = modes[i]
        if m == M_CAST and catch[i]:
            g = 1.0                         # the Silkspear catch falls
        elif m in (M_DS_ANTIC, M_DS_SPIKE, M_HURT_FREEZE, M_HURT_RECOIL, M_CAST, M_BIND):
            g = 0.0
        elif i > 0 and modes[i - 1] in (M_DS_ANTIC, M_DS_SPIKE, M_HURT_FREEZE, M_HURT_RECOIL, M_CAST, M_BIND):
            g = 1.0
        for _ in range(int(tr.fs[i])):
            vy = tr.vel[i, 1]
            if h <= 0 and not ground[i] and vy < 0:
                if not relinq_modes[i] and not noinp[i]:
                    g = params.air_hang_gravity
                h = 1.0
            if ground[i]:
                h = 0.0
            ctl = not relinq_modes[i] and not noinp[i]
            if ctl and g < 1.0:
                g += params.air_hang_accel * params.fdt
            if ctl and g < 1.0 and not jheld[i - 1 if i > 0 else 0]:
                g = 1.0
            g = min(g, 1.0)
        gs[i], hang[i] = g, h
    return gs, hang


def phase(tr: Trace, fdt: float | None = None, causal: bool = False) -> np.ndarray:
    """Render phase alpha per frame (the midpoint of phase_interval)."""
    return phase_interval(tr, fdt, causal)[0]


def phase_interval(tr: Trace, fdt: float | None = None, causal: bool = True
                   ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(midpoint, lo, hi) of the feasible render phase per frame from the logged dt / fs sequence: alpha_n =
    alpha_{n-1} + dt_n / fdt - fs_n must stay in [0, 1). The interval is propagated forward (causal: what the
    planner knows at that frame) and, with causal=False, also backward from the later frames (replays only)."""
    fdt = fdt or FDT
    n = len(tr)
    inc = tr.dt / fdt - tr.fs
    lo = np.zeros(n)
    hi = np.ones(n)
    a_lo, a_hi = 0.0, 1.0
    for i in range(n):                      # forward
        if i > 0:
            a_lo, a_hi = a_lo + inc[i], a_hi + inc[i]
        if not np.isfinite(a_lo) or a_hi <= 0.0 or a_lo >= 1.0 or a_lo > a_hi:
            a_lo, a_hi = 0.0, 1.0           # inconsistent (pause, scene load): restart
        a_lo, a_hi = max(a_lo, 0.0), min(a_hi, 1.0)
        lo[i], hi[i] = a_lo, a_hi
    if not causal and n:
        b_lo, b_hi = lo[-1], hi[-1]
        for i in range(n - 2, -1, -1):      # backward
            b_lo, b_hi = b_lo - inc[i + 1], b_hi - inc[i + 1]
            c_lo, c_hi = max(b_lo, lo[i]), min(b_hi, hi[i])
            if c_lo <= c_hi:
                lo[i], hi[i] = c_lo, c_hi
            b_lo, b_hi = lo[i], hi[i]
    return 0.5 * (lo + hi), lo, hi


# ---- incremental state tracker (the planner's per-tick start state) -------------------------------------------

_F32 = np.float32


def _acc32(acc: float, onset: bool, x: float, include: bool) -> float:
    """One step of _since32: the float32 running sum since the last onset (inf before any)."""
    if onset:
        return float(_F32(x)) if include else 0.0
    if not np.isfinite(acc):
        return acc
    return float(_F32(_F32(acc) + _F32(x)))


def _acc(acc: float, onset: bool, x: float, include: bool) -> float:
    """One step of _since (float64; used with integer counts only)."""
    if onset:
        return float(x) if include else 0.0
    return acc + x


class StateTracker:
    """The model state at the latest frame of a live STATE stream, updated in O(1) per frame: the same rows that
    state_table / estimate_state give for the last row of the whole history (tests check every row of the fixtures),
    without re-reading a history window every tick (Trace.from_states + estimate_state on a 240-frame tail cost
    about 2.5 ms per tick in Python; a push is under 0.1 ms, push_row 0.06 ms). It also gives the frame's contact
    events (derive_events) and whether the model owns the frame's motion (`modelled`, the rules of kin_check's
    categories: not a harness operation, scene change, hazard respawn, death or savestate slide, not locked by
    another FSM or charging a nail art, no time-scale change the hit-stop and world-freeze model does not explain,
    no hitch above frame_time_max), which ResidualMonitor needs.

        trk = StateTracker(params, terrain)
        trk.push(state)                       # every STATE (act.mask is the latched ACTION the game read)
        start = trk.state()                   # [K, 1], as estimate_state(trace, [last row], params, terrain=terrain)

    Masks come from act.mask (exact for the bot; the "input" stream needs a frame of look-ahead, Trace.from_states).
    Gaps (dropped STATEs) are not filled, as in state_table."""

    def __init__(self, params: HeroParams, terrain: Terrain2D | None = None, names: list[str] | None = None):
        self.params = params
        self.P = params.vector()
        self.terrain = terrain
        names = names or cstate_names()
        self._bit = [names.index(n) for n in _CS_USED]
        self._fl = {n: i for i, n in enumerate(_CS_USED)}
        self.n = 0
        self.S = np.zeros(K)
        self.events = 0
        self.modelled = False
        self.f = -1
        self.box = np.full(4, np.nan)
        self.mask = 0
        self.udt = 0.0
        self._p: dict[str, Any] = {}         # previous row
        self._a_lo, self._a_hi = 0.0, 1.0
        self._q = None
        self._phys0 = None
        self._acc = {k: np.inf for k in ("j", "pogo", "q_j", "q_a", "q_t", "atk_t", "atk_cd", "rsteps", "ds_rec",
                                         "bounce", "t_in", "t_after", "st_after", "mode_n", "cast_t", "inv")}
        self._last_q = {JQ: -1, AQ: -1, QQ: -1}
        self._last_kill = {JQ: -1, AQ: -1, QQ: -1}
        self._g, self._h = 1.0, 0.0
        self._ds_face = 0.0
        self._ds_seen = False
        self._dmg_side = 0.0
        self._fz: list[list] = []            # active hit-stop replays [ph, t, ts, k]
        self._tm_prev = np.full(len(TM_KEYS), np.nan)
        self._slide_left = 0
        self._other_in_hitstop = False
        self._wf = WF_IDLE.copy()

    # -- one row ---------------------------------------------------------------------------------------------------
    def push(self, s: dict) -> None:
        """One STATE dict (as Trace.from_states reads it)."""
        h = s.get("hero")
        g = s.get("game") or {}
        tm = (h or {}).get("tm")
        tm_row = np.array([float(tm[k]) if isinstance(tm, dict) and tm.get(k) is not None else np.nan
                           for k in TM_KEYS]) if tm else np.full(len(TM_KEYS), np.nan)
        a = (h or {}).get("alpha")
        load = False
        dmg, mk, fz = 0, 0, 0
        for ev in s.get("ev") or ():
            k = ev.get("k")
            d = ev.get("d") or {}
            if k == "harness" and d.get("op") == "savestate.load":
                load = True
            if k == "damage":
                side = d.get("side")
                dmg = -1 if side == "left" else 1 if side == "right" else dmg
            elif k == "freeze" and d.get("phase") == "start":
                typ = str(d.get("type"))
                fz |= FZ_RECOIL if "StartRecoil" in typ else _FZ_TYPES.get(typ, FZ_OTHER)
            else:
                mk |= _MARK_KINDS.get(k, 0)
        if fz & ~(FZ_RECOIL | FZ_ENEMY_DEATH) or (fz & FZ_ENEMY_DEATH and not fz & FZ_RECOIL):
            mk |= MK_FREEZE
        row: dict[str, Any] = {"f": s["f"], "fs": int(s.get("fs") or 0), "dt": float(s.get("dt") or 0.0),
                               "udt": float(s.get("udt") or 0.0),
                               "ts": float(s.get("ts", 1.0) if s.get("ts") is not None else 1.0),
                               "mask": int((s.get("act") or {}).get("mask", 0) or 0), "dmg": dmg, "marks": mk,
                               "freeze": fz, "tm": tm_row, "alpha": float(a) if a is not None else np.nan,
                               "load": load}
        if not h or not h.get("box") or not h.get("cstate"):
            row.update(phys=np.array([np.nan, np.nan]), vel=np.array([np.nan, np.nan]), box=np.full(4, np.nan),
                       facing=0, hero_state=-1, relinq=False, cs=np.zeros(len(self._bit), dtype=bool), silk=0,
                       clip=None, spell=None, valid=False)
        else:
            b = h["box"]
            words = h["cstate"]
            pause = s.get("pause") or {}
            row.update(phys=np.array([0.5 * (b[0] + b[2]), b[1] + self.params.foot]),
                       vel=np.asarray(h.get("vel") or [0.0, 0.0], dtype=np.float64)[:2],
                       box=np.asarray(b[:4], dtype=np.float64), facing=int(h.get("facing", 1)),
                       hero_state=int(h.get("hero_state", -1)), relinq=bool(h.get("control_relinquished")),
                       cs=np.array([bool((words[i >> 6] >> (i & 63)) & 1) for i in self._bit]),
                       silk=int(h.get("silk") or 0), clip=(h.get("anim") or {}).get("clip"),
                       spell=(h.get("spell") or [None])[0],
                       valid=g.get("gs", 4) == 4 and not g.get("paused") and not pause.get("inv", False))
        self.push_row(row)

    def push_row(self, r: dict) -> None:
        """One row in Trace terms: f, fs, dt, udt, ts, phys [2], vel [2], box [4], facing, hero_state, relinq,
        cs [len(_CS_USED)] bool, mask, silk, clip, spell (names), dmg, marks, freeze, valid, tm [15] (NaN: not
        exported), alpha (NaN: not exported), load (a savestate.load harness op in this frame)."""
        p, P, pr = self.params, self.P, self._p
        i = self.n
        first = i == 0
        cs = r["cs"]
        fl = lambda name: bool(cs[self._fl[name]])  # noqa: E731
        was = (lambda name: bool(pr["cs"][self._fl[name]])) if not first else (lambda name: False)  # noqa: E731
        steps = float(r["fs"])
        dt = float(r["dt"])
        mask = int(r["mask"])
        pmask = 0 if first else int(pr["mask"])
        # mode (classify_modes)
        hs7 = r["hero_state"] == HS_NO_INPUT
        md = M_NORMAL
        if r["relinq"]:
            md = M_LOCKED
        if r["clip"] in CAST_CLIPS and (r["relinq"] or hs7):
            md = M_CAST
        if (fl("isBinding") or r["spell"] in BIND_SPELLS) and (r["relinq"] or hs7):
            md = M_BIND
        if fl("downSpikeAntic"):
            md = M_DS_ANTIC
        if fl("downSpiking"):
            md = M_DS_SPIKE
        if fl("recoiling") and hs7:
            md = M_HURT_RECOIL
        if fl("recoilFrozen"):
            md = M_HURT_FREEZE
        pmd = None if first else pr["mode"]
        on = lambda name: fl(name) and not was(name)  # noqa: E731
        S = np.zeros(K)
        # phase interval, forward (phase_interval, causal)
        if not first:
            inc = dt / p.fdt - steps
            self._a_lo, self._a_hi = self._a_lo + inc, self._a_hi + inc
        if not np.isfinite(self._a_lo) or self._a_hi <= 0.0 or self._a_lo >= 1.0 or self._a_lo > self._a_hi:
            self._a_lo, self._a_hi = 0.0, 1.0
        self._a_lo, self._a_hi = max(self._a_lo, 0.0), min(self._a_hi, 1.0)
        S[ALPHA], S[ALO], S[AHI] = 0.5 * (self._a_lo + self._a_hi), self._a_lo, self._a_hi
        # pose
        phys = r["phys"]
        if first:
            self._phys0 = phys.copy()
            self._q = phys.copy()
        if steps > 0:
            self._q = (pr["phys"] if not first else self._phys0).copy()
        S[PX], S[PY] = phys
        S[SX], S[SY] = phys
        S[QX], S[QY] = self._q
        S[VX], S[VY] = r["vel"]
        S[FACE] = 1.0 if r["facing"] >= 0 else -1.0
        ground = fl("onGround")
        S[GROUND] = float(ground)
        S[MODE] = md
        S[SILK] = r["silk"]
        S[PREV] = mask
        S[MOVE] = (1.0 if mask & B_RIGHT else 0.0) - (1.0 if mask & B_LEFT else 0.0)
        S[JHELD] = float((mask & B_JUMP) != 0)
        # jumps
        ac = self._acc
        jumping = fl("jumping")
        j_on = on("jumping")
        pogo_on = on("downSpikeBouncing")
        ac["j"] = _acc(ac["j"], j_on, steps, False)
        ac["pogo"] = _acc(ac["pogo"], j_on, float(pogo_on), True)
        pogo_j = ac["pogo"] > 0
        S[JUMPING] = float(jumping)
        S[JSTEPS] = ((p.pogo_jump_steps if pogo_j else 0) + ac["j"]) if jumping else 0.0
        jd = (p.pogo_jumped_steps if pogo_j else 0) + ac["j"]
        S[JDSTEPS] = jd if np.isfinite(jd) else 100.0
        att = fl("attacking")
        a_on = on("attacking")
        ds_on = on("downSpikeAntic")
        # input queues
        castbind = md in (M_CAST, M_BIND)
        c_on = castbind and not (pmd in (M_CAST, M_BIND))
        for row, bit, started, key in ((JQ, B_JUMP, j_on, "q_j"), (AQ, B_ATTACK, a_on or ds_on, "q_a"),
                                       (QQ, B_QUICKCAST, c_on, "q_t")):
            held = (mask & bit) != 0
            q_on = held and not (pmask & bit) and not started
            if q_on:
                self._last_q[row] = i
            if not held or started:
                self._last_kill[row] = i
            ac[key] = _acc(ac[key], q_on, steps, False)
            alive = self._last_q[row] >= 0 and self._last_q[row] > self._last_kill[row]
            S[row] = ac[key] if alive else -1.0
        # gravity scale and air hang (_replay_gravity)
        g, hh = self._g, self._h
        relq = md in RELINQUISHED
        noinp = md in NO_INPUT
        if md == M_CAST and r["clip"] == "NeedleThrow Catch":
            g = 1.0
        elif md in (M_DS_ANTIC, M_DS_SPIKE, M_HURT_FREEZE, M_HURT_RECOIL, M_CAST, M_BIND):
            g = 0.0
        elif not first and pmd in (M_DS_ANTIC, M_DS_SPIKE, M_HURT_FREEZE, M_HURT_RECOIL, M_CAST, M_BIND):
            g = 1.0
        jheld_prev = ((pmask if not first else mask) & B_JUMP) != 0
        for _ in range(int(r["fs"])):
            vy = r["vel"][1]
            if hh <= 0 and not ground and vy < 0:
                if not relq and not noinp:
                    g = p.air_hang_gravity
                hh = 1.0
            if ground:
                hh = 0.0
            ctl = not relq and not noinp
            if ctl and g < 1.0:
                g += p.air_hang_accel * p.fdt
            if ctl and g < 1.0 and not jheld_prev:
                g = 1.0
            g = min(g, 1.0)
        self._g, self._h = g, hh
        S[GS], S[AIRHANG] = g, hh
        # attacks
        S[ATTACKING] = float(att)
        ac["atk_t"] = _acc32(ac["atk_t"], a_on, dt, False)
        S[ATK_T] = ac["atk_t"] if att else 0.0
        ac["atk_cd"] = _acc32(ac["atk_cd"], a_on or ds_on, dt, True)
        cd = float(_F32(p.attack_cooldown)) - ac["atk_cd"]
        S[ATK_CD] = max(cd, 0.0) if np.isfinite(cd) else 0.0
        # nail recoil
        rl, rr = fl("recoilingLeft"), fl("recoilingRight")
        ac["rsteps"] = _acc(ac["rsteps"], on("recoilingLeft") or on("recoilingRight"), steps, False)
        S[RDIR] = -1.0 if rl else (1.0 if rr else 0.0)
        S[RSTEPS] = max(p.recoil_steps - ac["rsteps"], 0.0) if S[RDIR] != 0 else 0.0
        # downspike
        if ds_on:
            self._ds_face = 1.0 if r["facing"] >= 0 else -1.0
            self._ds_seen = True
        S[DS_HS] = self._ds_face * p.ds_speed if self._ds_seen else 0.0
        rec = fl("downSpikeRecovery")
        ac["ds_rec"] = _acc32(ac["ds_rec"], on("downSpikeRecovery"), dt, True)
        S[DS_REC] = ac["ds_rec"] if rec else -1.0
        bnc = fl("downSpikeBouncing")
        ac["bounce"] = _acc(ac["bounce"], pogo_on, steps, False)
        S[BOUNCE] = ac["bounce"] if bnc else -1.0
        # time in mode
        m_on = first or md != pmd
        ac["t_in"] = _acc32(ac["t_in"], m_on, dt, True)
        ac["t_after"] = _acc32(ac["t_after"], m_on, dt, False)
        ac["st_after"] = _acc32(ac["st_after"], m_on, steps * float(_F32(p.fdt)), False)
        ac["mode_n"] = _acc(ac["mode_n"], m_on, 1.0, False)
        mt = ac["st_after"] if md == M_DS_SPIKE else (ac["t_in"] if md == M_DS_ANTIC else ac["t_after"])
        S[MODE_T] = mt if np.isfinite(mt) else 0.0
        S[MODE_N] = ac["mode_n"] if np.isfinite(ac["t_after"]) else 0.0
        S[TS] = r["ts"]
        # hit-stop replay (_freeze_replay): the latest hit's replay wins
        if on("recoilFrozen"):
            self._fz.append([0, _F32(0.0), 0.0, 0])
        out = (0.0, 0.0, 0.0, 1.0)
        keep = []
        u = _F32(r["udt"])
        for st in self._fz:
            ph, t, tsv, k = st
            res = None
            ended = False
            if ph == 0 and k >= p.hurt_wait_skip + 1:
                t = _F32(t + u)
                if t >= _F32(p.hurt_wait):
                    ph, t = 1, _F32(0.0)
                    res = (ph, 0.0, k + 1, tsv)
            elif ph == 1:
                t = _F32(t + u)
                tsv = min(float(t) / p.hurt_ramp, 1.0)
                if t >= _F32(p.hurt_ramp):
                    res = (2, 0.0, k + 1, 1.0)
                    ended = True
            if res is None:
                res = (ph, float(t), k + 1, tsv)
            out = res
            k += 1
            if not ended and k < 40:
                keep.append([ph, t, tsv, k])
        self._fz = keep
        if md == M_HURT_FREEZE:
            S[PHASE] = min(out[0], 1.0)
            S[MODE_T] = out[1]
            S[MODE_N] = out[2]
        if on("recoilFrozen"):
            self._dmg_side = float(r["dmg"] if r["dmg"] != 0 else (1 if r["facing"] >= 0 else -1))
        S[HVX] = -self._dmg_side * p.hurt_velocity
        S[HVY] = p.hurt_velocity * p.hurt_vy_ratio
        # Silkspear phase
        cph = 1.0 if r["clip"] == "NeedleThrow Throwing" else (2.0 if r["clip"] == "NeedleThrow Catch" else 0.0)
        cast = md == M_CAST
        p_on = cast and (pmd != M_CAST or cph != pr.get("cph", 0.0))
        ac["cast_t"] = _acc32(ac["cast_t"], p_on, dt, False)
        if cast:
            S[PHASE] = cph
            if np.isfinite(ac["cast_t"]):
                S[MODE_T] = ac["cast_t"]
        inv = fl("invulnerable")
        ac["inv"] = _acc32(ac["inv"], on("invulnerable"), dt, False)
        left = float(_F32(p.invul_time)) - ac["inv"]
        S[INV_T] = max(left, 0.0) if inv and np.isfinite(left) else 0.0
        S[LEDGE] = 0.0
        # world freezes (_wf_replay)
        bits = int(_freeze_events(np.array([int(r["freeze"])], dtype=np.int64))[0])
        if on("recoilFrozen") and not first and pmd == M_BIND and pr["t_after"] < p.bind_break_before:
            bits |= EV_FZ_BIND_BREAK
        if bits or self._wf[0] >= 0:
            self._wf = _wf_row(self._wf, bits, float(r["udt"]), P)
        S[WF_PH:WF_TGT + 1] = self._wf
        if self._wf[0] >= 0:
            S[TS] = out[3] if md == M_HURT_FREEZE else 1.0
        # exported timers and phase (_apply_exported)
        if np.isfinite(r["alpha"]):
            S[ALPHA] = S[ALO] = S[AHI] = r["alpha"]
        tmv = np.asarray(r["tm"], dtype=np.float64)
        if np.isfinite(tmv).any():
            col = dict(zip(TM_KEYS, tmv))

            def put(row: int, v: float, where: bool = True) -> None:
                if np.isfinite(v) and where:
                    S[row] = v

            put(INV_T, max(col["inv"], 0.0) if np.isfinite(col["inv"]) else np.nan)
            put(MODE_T, p.hurt_recoil_time - col["recoil"], md == M_HURT_RECOIL)
            put(RSTEPS, col["recoil_steps"], S[RDIR] != 0)
            put(ATK_CD, max(col["atk_cd"], 0.0) if np.isfinite(col["atk_cd"]) else np.nan)
            put(ATK_T, col["atk_t"], S[ATTACKING] > 0)
            put(JSTEPS, col["jump_steps"], S[JUMPING] > 0)
            put(JDSTEPS, col["jumped_steps"])
            put(MODE_T, col["ds"], md in (M_DS_ANTIC, M_DS_SPIKE))
            put(DS_REC, col["ds_rec"], S[DS_REC] >= 0)
            put(GS, col["grav"])
            for row, k, j, bit in ((JQ, "qj", 12, B_JUMP), (AQ, "qa", 13, B_ATTACK), (QQ, "qt", 14, B_QUICKCAST)):
                v, before = col[k], self._tm_prev[j]
                grew = np.isfinite(before) and np.isfinite(v) and v > before and (mask & bit) != 0
                if np.isfinite(v) and (S[row] >= 0 or grew):
                    S[row] = max(v, 0.0)
        self._tm_prev = tmv
        # contact events (derive_events)
        ev = 0
        if on("recoilingLeft"):
            ev |= EV_RECOIL_L
        if on("recoilingRight"):
            ev |= EV_RECOIL_R
        if pogo_on:
            ev |= EV_POGO
        if r["clip"] == "NeedleThrow Catch" and pr.get("clip") != "NeedleThrow Catch" and md == M_CAST:
            ev |= EV_CATCH
        if not first and r["silk"] > pr["silk"]:
            ev |= EV_SILK
        vy, vy0 = r["vel"][1], (0.0 if first else pr["vel"][1])
        rising = vy0 > 0 or ((was("jumping") if not first else False) and r["fs"] > 0)
        if (vy == 0 and rising and not ground and md == M_NORMAL and pmd == M_NORMAL and
                (att or fl("upAttacking"))):
            ev |= EV_RECOIL_DOWN
        if on("recoilFrozen"):
            ev |= EV_HURT_L if self._dmg_side < 0 else EV_HURT_R
        if md == M_LOCKED and pmd != M_LOCKED:
            ev |= EV_LOCK
        if md != M_LOCKED and pmd == M_LOCKED:
            ev |= EV_UNLOCK
        ev |= bits & ~EV_FZ_BIND_BREAK
        # does the model own this frame's motion (kin_check categories)
        if r.get("load"):
            self._slide_left = SLIDE_SPAN[1]
        slide = self._slide_left > 0
        self._slide_left = max(self._slide_left - 1, 0)
        # a freeze the model has no preset for, or a BindBreak its rule did not start
        other = (r["freeze"] & FZ_OTHER) != 0 or ((r["freeze"] & FZ_BIND_BREAK) != 0 and not bits & EV_FZ_BIND_BREAK)
        if md == M_HURT_FREEZE:
            self._other_in_hitstop = self._other_in_hitstop or other or bool(pr.get("other", False))
        elif pmd != M_HURT_FREEZE:
            self._other_in_hitstop = False
        world = (r["ts"] < 0.999 and md != M_HURT_FREEZE and self._wf[0] < 0) or other or self._other_in_hitstop
        bad_marks = (r["marks"] & (MK_HARNESS | MK_HAZARD | MK_SCENE | MK_DEATH)) != 0
        valid = bool(r["valid"]) and np.isfinite(r["box"][0])
        gap = not first and r["f"] != pr["f"] + 1
        self.modelled = bool(valid and not gap and not bad_marks and not slide and md != M_LOCKED and
                             not fl("nailCharging") and not world and r["udt"] <= p.frame_time_max)
        if md != M_HURT_FREEZE and pmd == M_HURT_FREEZE:
            self._other_in_hitstop = False
        # terrain contact (estimate_state)
        if self.terrain is not None:
            near = _on_ground(S[PX:PX + 1], S[PY:PY + 1], P, self.terrain.hseg)[0]
            S[TOUCH] = float(near and S[GROUND] <= 0 and S[VY] < 0)
        self.S = S
        self.events = ev
        self.f, self.box, self.mask, self.udt = r["f"], r["box"], mask, r["udt"]
        self._p = {"cs": cs, "mask": mask, "mode": md, "phys": phys, "vel": r["vel"], "silk": r["silk"],
                   "clip": r["clip"], "cph": cph, "f": r["f"], "other": other, "t_after": ac["t_after"]}
        self.n += 1

    def state(self) -> np.ndarray:
        """[K, 1] model state at the latest frame."""
        return self.S[:, None].copy()


# ---- runtime residual monitor (DESIGN §3.5.2) -----------------------------------------------------------------

# alarm levels of ResidualMonitor over its last 600 windows at 30 frames (misses allowed: (1 - 0.85) * 600 = 90), with
# room above the worst of 837 k frames of held-out play (trial i0_000, live i1_000, i2_001, i3_000; kin_check --monitor:
# at most 65 windows missing the hull, 58 by more than 0.5 u, after clusters of pogo / recoil / hit windows the model
# misses); a broken model (0.3 u off) misses every window
MONITOR_ALARM_WITHIN = 0.85
MONITOR_ALARM_FAR = 80


class ResidualMonitor:
    """Runtime residual monitor (DESIGN §3.5.2; I4 confidence "kinematics", DESIGN §3.7.2). It checks the claim the
    planner relies on, on the commands that were executed: from the model state at an anchor frame a it re-rolls the
    latched masks the game read (STATE act.mask) and the contact events it observed (the threat layer's job at plan
    time) at nominal timing with the timing lanes, and asks whether the observed collider box h frames later lies in
    the lanes' hull dilated by tol (Rollout.bound, variants "bounds"). Re-rolling the executed stream makes replans
    irrelevant: a plan abandoned after one frame is never scored. Frames the model does not own (StateTracker
    .modelled False: harness operations, scene changes, hazard respawns, deaths, savestate slides, control taken by
    another FSM, nail arts, world freezes, hitches above frame_time_max, gaps) drop every anchor whose window holds
    them. The nominal lane's centre error is reported beside it (a point prediction misses one-step timing branches
    the history cannot resolve, so it is no alarm criterion).

        mon = ResidualMonitor(params, terrain)
        trk.push(state); mon.update(trk)       # each STATE: score the anchors whose horizon ends now, anchor this one
        mon.status()                           # per horizon: n, within, p99, max; "state": unknown / ok / degraded
        mon.confidence()                       # share within at the longest horizon; None while unknown

    Unknown is never safe: before min_n scored windows (after construction or reset(), which a new scene or terrain
    needs) the state is "unknown" and confidence() None; pass it to safety.invariants.i4 only when it is not None (a
    missing module counts as below its threshold). "degraded" when, among the last `window` scored windows at the
    longest horizon, more than (1 - alarm_within) * window miss the hull by tol or more than alarm_far by far_u
    (counts, so a ring still filling after a reset is not judged on a few windows). Held-out play (kin_check
    --monitor on trial i0_000, live i1_000, i2_001, i3_000: 837 k frames, 815 k windows scored at 30 frames, 1.1 %
    dropped) puts 99.36-99.79 % of the windows inside the hull by recording (the nominal lane 90.0-91.2 %, at 1 frame
    99.9 %) and never reaches "degraded"; a model 0.3 u off does within the window (test). Cost: about 0.17 ms per
    frame (one compiled rollout of the due anchors, 9 lanes), plus StateTracker.push under 0.1 ms."""

    def __init__(self, params: HeroParams, terrain: Terrain2D | None = None, horizons: tuple[int, ...] = (1, 6, 30),
                 tol: float = 0.1, window: int = 600, min_n: int = 60, alarm_within: float = MONITOR_ALARM_WITHIN,
                 far_u: float = 0.5, alarm_far: int = MONITOR_ALARM_FAR, variants: str | tuple = "bounds",
                 stride: int = 1):
        self.params, self.terrain = params, terrain
        self.horizons = tuple(sorted(horizons))
        self.tol, self.window, self.min_n = tol, window, min_n
        self.alarm_within, self.far_u, self.alarm_far = alarm_within, far_u, alarm_far
        self.variants, self.stride = variants, max(int(stride), 1)
        self.anchors: dict[int, np.ndarray] = {}
        self.cmd: dict[int, tuple[int, int]] = {}
        self.exc = {h: np.full(window, np.nan) for h in self.horizons}
        self.err = {h: np.full(window, np.nan) for h in self.horizons}
        self.k = {h: 0 for h in self.horizons}
        self.scored = {h: 0 for h in self.horizons}
        self.inside = {h: 0 for h in self.horizons}           # all-time counts within tol: hull, nominal lane
        self.nominal_inside = {h: 0 for h in self.horizons}
        self.dropped = 0
        self.last_f: int | None = None

    def reset(self) -> None:
        """Forget everything (a new scene: other terrain, other evidence)."""
        self.__init__(self.params, self.terrain, self.horizons, self.tol, self.window, self.min_n, self.alarm_within,
                      self.far_u, self.alarm_far, self.variants, self.stride)

    def anchor(self, frame: int, state: np.ndarray) -> None:
        """The model state at `frame` (StateTracker.state() / estimate_state), after observe(frame, ...)."""
        if frame % self.stride == 0:
            S = np.asarray(state, dtype=np.float64)
            self.anchors[frame] = (S[:, 0] if S.ndim == 2 else S).copy()

    def invalidate(self) -> None:
        """Drop every pending anchor (the caller knows the motion is not the model's)."""
        self.dropped += len(self.anchors)
        self.anchors.clear()

    def observe(self, frame: int, box: np.ndarray, mask: int, events: int = 0, modelled: bool = True) -> None:
        """One STATE: the collider box, the latched mask the game read and the contact events of `frame`."""
        if self.last_f is not None and frame != self.last_f + 1:
            self.invalidate()
        self.last_f = frame
        self.cmd[frame] = (int(mask), int(events))
        H = self.horizons[-1]
        for f in [f for f in self.cmd if f < frame - H]:
            del self.cmd[f]
        if not modelled or not np.isfinite(np.asarray(box, dtype=np.float64)).all():
            self.invalidate()
            return
        due = [(a, frame - a) for a in self.anchors if frame - a in self.horizons]
        if due:
            T = max(h for _, h in due)
            masks = np.zeros((len(due), T), dtype=np.int64)
            ev = np.zeros((len(due), T), dtype=np.int64)
            for j, (a, h) in enumerate(due):
                for t in range(h):
                    masks[j, t], ev[j, t] = self.cmd[a + 1 + t]
            start = np.stack([self.anchors[a] for a, _ in due], axis=1)
            r = rollout(start, masks, self.params, self.terrain, events=ev, variants=self.variants)
            b = np.asarray(box, dtype=np.float64)
            c = 0.5 * (b[:2] + b[2:])
            for j, (a, h) in enumerate(due):
                u = r.bound[j, h]
                e = max(u[0] - b[0], u[1] - b[1], b[2] - u[2], b[3] - u[3], 0.0)
                n = r.box[j, h]
                slot = self.k[h] % self.window
                self.exc[h][slot] = e
                self.err[h][slot] = float(np.hypot(*(0.5 * (n[:2] + n[2:]) - c)))
                self.k[h] += 1
                self.scored[h] += 1
                self.inside[h] += int(e <= self.tol)
                self.nominal_inside[h] += int(self.err[h][slot] <= self.tol)
        for a in [a for a in self.anchors if frame - a >= H]:
            del self.anchors[a]

    def update(self, trk: "StateTracker") -> None:
        """observe() the tracker's latest frame, then anchor its state."""
        self.observe(trk.f, trk.box, trk.mask, trk.events, trk.modelled)
        if trk.modelled:
            self.anchor(trk.f, trk.S)

    def status(self) -> dict[str, Any]:
        out: dict[str, Any] = {"horizons": {}, "dropped": self.dropped}
        for h in self.horizons:
            e = self.exc[h][np.isfinite(self.exc[h])]
            d = self.err[h][np.isfinite(self.err[h])]
            out["horizons"][h] = {"n": int(len(e)), "scored": self.scored[h],
                                  "within": float(np.mean(e <= self.tol)) if len(e) else None,
                                  "misses": int(np.sum(e > self.tol)), "far": int(np.sum(e > self.far_u)),
                                  "p99": float(np.percentile(e, 99)) if len(e) else None,
                                  "max": float(e.max()) if len(e) else None,
                                  "nominal_within": float(np.mean(d <= self.tol)) if len(d) else None}
        acc = out["horizons"][self.horizons[-1]]
        if acc["n"] < self.min_n:
            out["state"], out["confidence"] = "unknown", None
        else:
            # counts, not shares, so a ring that is still filling (after a reset) is not judged on a few windows
            good = acc["misses"] <= (1.0 - self.alarm_within) * self.window and acc["far"] <= self.alarm_far
            out["state"], out["confidence"] = ("ok" if good else "degraded"), acc["within"]
        out["ok"] = out["state"] == "ok"
        return out

    def confidence(self) -> float | None:
        return self.status()["confidence"]


def describe_state(S: np.ndarray, i: int = 0) -> dict[str, Any]:
    """One lane of a state array as {row name: value} (debugging, logs)."""
    col = S[:, i] if S.ndim == 2 else S
    d = {name: float(col[j]) for j, name in enumerate(ROW_NAMES)}
    d["mode"] = MODE_NAMES[int(col[MODE])]
    return d
