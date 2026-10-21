# Forum map v2 - the search-based planner (spec, 2026-10-20)

The person's decision (2026-10-20): stop adding hand-written tactics; build the map now. Acceptance: the five
moves below must be FOUND BY THE SEARCH from primitives and models, not scripted. The design is the result of the
lead's conversation with the person on 2026-10-19 / 20 (main docs/plans/forum_planner_plan.md, bold notes of those
days: the three layers, the envelope design, branch points, combo discovery, silk not a constraint).

## 0. Acceptance

1. P1 the Clawline in every state: an Idle Clapper (its reaction comes 12-18 f after the hook: slam -> the second
   window, cast -> head pogos, evade -> the chase), every antic (slam: a press by antic ~11 -> the first window
   (5-11) or the second (0-4 / earlier); cast: any time, free; jump antic: the take-off hook), the other Clapper locked
   by the buddy rule = a free hit.
2. P2 the umbrella close -> drop -> strike (the close frame chosen by the search).
3. P3 the facing steered by the contact side (its next move faces her side at the contact frame; keep it facing the
   wall so its evades go to the middle; cross to the middle side in a slam antic).
4. P4 ride a jumping Clapper up (down slashes on its rising body, every ~19 f) and float down over / behind its landing
   (the big-rune dome is ~3.45 u high over the landing point). Once up high, nothing reaches her for a while.
5. P5 a Clapper standing on her landing spot -> down slash it instead of landing on it.
Plus regression: the search must rediscover the known scripts in their own situations (CLAWSTRIKE: hop + Clawline at
antic 5-11 + down slash on Slam 0; the slam playbook's strike; JUMPTRAP's pass under; the low hop over bombs).
Report per move: found (same kind) / found (different, better by the model) / not found (why: missing primitive,
missing mechanic, horizon, timing grid, infeasible) / found but fails live (model error).

## 1. Architecture (three layers)

L1 ENEMY MODEL (per enemy, per move; knowledge, measured once):
- Source of truth = POLYGONS (boxes / circles / polygons of the game colliders) per frame in the enemy's own frame
  (origin its transform, facing +x; mirror for facing), per timing variant (e.g. slam antic 47 / 48 / 49, Slam 0 4 / 5),
  with a kind per polygon: damage / body / pogo-able / tink (bounces the nail).
- Reactions and rules (closed loop, they depend on her plan): Idle: TOOK DAMAGE -> Dmg Attack 12-18 f after the hit
  (mostly 18; find where the spread comes from); Idle 0.65 s -> Walk; Walk >= 0.25 s and her in Slam Range -> Close
  Range (SLAM / EVADE / CAST 1/3; after Evaded only SLAM / CAST); out of range -> Far Range (JUMP 0.5 / CAST 0.25 /
  JUMP CAST 0.25); Will Evade (random at Idle entry) -> Evade at >= 0.25 s in range; an evade with its wall < ~6 u
  behind -> the escape jump; the buddy lock (Close / Far Range read the other's Is Attacking -> CANCEL to Idle; the flag
  from Slam / Spell / Jump / Cast Slam Antic to Slam 2 / Cast 2); every start state first faces her (FaceObjectV2,
  turns >= 0.5 s apart); Jump Aim reads her x (target = her x - 5 x its facing, travel 0.916 x clamp(+-12), wall push);
  Slam Range = its pos +-8.05 u in x and pos -4.46 .. +3.37 u in y (her collider in the trigger).
- API: predict(enemy state, her planned path) -> per frame: damage / body / pogo polygons for each outcome branch with
  probabilities, and the reveal frame of each branch (when she can see which one it is).
- Validation (the rule validate-predictions-first): frame accuracy per move on the recordings (timing and geometry),
  then the person's eye check in the overlay before any live use.

L2 HERO ENVELOPES (the person's design; one for Hornet, every enemy):
- Horizontal: normal ground / air control is instant (vx = 8.25 x direction, no acceleration; kinematics.py), so the
  reachable x after n frames is exactly the interval between "all left" and "all right" - no key enumeration (3^n).
  The umbrella float HAS horizontal inertia (accel 1.0 / decel 0.25 per physics step; the antic 8.5): carry vx as a
  state inside the float (the drift 4.4 -> 2.5 u in ~20 f with no key). The ground sprint accelerates (1.1 per step)
  and skids when released after Sprint Grace. Horizontal and vertical stay decoupled.
- Vertical modes: normal (g ~60 u/s^2, the max fall), the float (vy -> -6 u/s at 0.13 per step; Inflate 12 f at +0.5),
  the jump rise (hold 18.6 u/s; the release frame is a parameter: an envelope between the shortest and the longest
  hold - no separate table).
- Carved-out blocks (committed motion, the envelope continues from their end): the umbrella opening (Antic 6 f +
  Inflate 12 f; the earliest close 17 f after the open; a re-open 13 f after a close at the earliest), the closing
  (Deflate ~6-7 f; the attack in the float plays a Deflate first: 2 f measured in SP13a, ~8 f seen in the air show -
  calibrate), the dash (0.1 s at 28 u/s), the Clawline (antic 2-10 hover drifting ~1.2 u toward it, hook +10-11, dash
  +19-22 at 70 u/s for 3-7 f stopping ~2 u before the body, control +26-34; no i-frames; the hooked one's contact off
  to control + 0.2 s; the attack 9 f after control; at control a forced bounce unless she acts), the pogo bounce (the
  contact box + 4.09 u, apex +22/23 f, i-frames 8 physics steps ~9 f; jump in the contact -6 .. +2 changes nothing;
  jump from +3 = the umbrella), the slash recoil, a hit's knock-back.
- State flags: the umbrella (closed / opening k / open / closing k), the dash (ready / cooldown; the air dash restored
  by a pogo? - measure), the attack cooldown (19 f press to press; the down slash active +3 .. +9). SILK IS NOT A
  STATE (memory silk-not-a-constraint: a hitless bot never binds, the Silk Heart regenerates).
- With danger: propagate frame by frame (dilate by one frame's reach, subtract the danger cells); a witness path
  (concrete keys) by backtracking from the chosen target cell. Obstacle-free envelopes are precomputed per mode and
  entry state (forum_reach.npz is the precursor) and applied by translation.
- The down slash polygon (pogo_model DOWN / DOWN_ALT, alternating) spans ~3.2 u (1.25-1.5 u past the hurtbox on each
  side at her feet's height, narrowing to ~0.35 u past it 1 u below her feet; the lowest point ~1.17 u below her
  feet); the hurtbox is 0.4554 x 2.2498 u, centre 0.38 u below the transform.

THE PERSON'S REFINEMENT OF L2 (2026-10-20 evening):
- The envelope is fight-independent and precomputed before the fight (per hero kit: crest, tools, abilities): tables
  'reachable after 1, 2, 3, ... frames', with HER CURRENT POSITION AS THE ORIGIN, independent of her map x / y,
  keyed by her movement state. Only CONTROLLABLE states get tables (a dash's 2nd frame has no choice: it is a
  deterministic carve-out to the next controllable state). In the air the tables assume infinite height (no floor);
  terrain (floor, walls, ceiling) and danger are applied at use time.
- The state key must hold everything that changes the future reach: the mode (ground / air normal / float /
  opening / closing), vy (binned: a rise at +10 and a fall at -5 reach different places), the jump-hold phase, the
  float's vx (inertia), the dash available or not. Per cell store the reachable state range (vy range, flags), so a
  continuation can start from a chosen (position, state).
- Use: the search runs inside the envelope until the first frame it touches any predicted damage box or terrain -
  that frame IS the branch time (generated automatically); until then every point inside is free. To go on, pick a
  waypoint inside the envelope at the branch time (a position + one of its reachable states; several candidates, a
  small tree) and restart from the reused table of that state. Paths to a chosen point are cheap (instant run: hold
  toward it m frames, then release).
- A fixed future time T: as she moves, the envelope for T shrinks (the future collapses into the past). Use it as the
  commitment monitor: a planned target at T stays valid while it is inside the shrinking envelope (the hysteresis).
- Where dangers interleave inside one segment (weaving between two boxes), the frame-by-frame propagation with the
  danger subtracted complements the waypoint restarts.

THE CLAWLINE IN THE TWO LAYERS (the person, 2026-10-20 evening):
- Windows are bound to the enemy (time relative to its event, position relative to it and its facing). At decision
  time the search transforms each window to map coordinates and time with the predicted enemy state, including the
  Clawline's PRESS region of a Clawline window (in front of its body within the 10.5 u ray, her box bottom in the
  band against its body, the press frames, e.g. slam antic 5-11), and asks whether her envelope contains it (with a
  usable state). After the press the Clawline is a deterministic block; the window's later steps follow it.
- The Clawline is also plain MOBILITY: unhooked it still pulls her flat ~5.7-7.8 u at the same height (10 recorded
  cases: measure it in M0) - fight-independent, so it belongs in the precomputed envelope tables like the dash;
  hooked it carries her to ~2 u before the target's body and bounces her ~4 u up - target-dependent, so it is added
  at use time (a hook on an Idle Clapper is a hit and triggers its reaction: the enemy model sees it). Slower than
  the dash for short hops (control 26-34 f), faster for long ones (70 u/s).

L3 SEARCH:
- Candidates = the combo library (the existing scripts as macro actions with their calibrated timings) + single
  primitives at branch points. Branch points = the end of her discrete commitments (a slash's lock, the Clawline's
  control, a pogo contact / its i-frames' end, the umbrella's opening end, a release of the jump, a landing) and the
  enemy's reveal frames (its move choice visible on the antic's first frame). Continuous controls (left / right, the
  jump hold, the umbrella timing, the drift) are parameters inside a segment: a coarse grid (2-4 f) then +-1-2 f
  refinement near tight windows; re-plan every tick (receding horizon).
- Enemy uncertainty: a candidate must be safe for EVERY enemy outcome during its committed part, allowing her
  reactive steering after the reveal + 1-2 f reaction lag (not one fixed key string for all outcomes); after the
  committed part every outcome must still have a safe continuation (the coarse exit check - this is what catches the
  jump traps set at Jump Aim 38-45 f ahead); the value = the expected hits over the outcomes (e.g. 1/3 each).
- Horizons: the near part exact (polygons, or the existing 0.05 u per-frame tables of hitbox_tables.py) to the
  candidate's next branch point or its end; the far part coarse (~0.25 u cells, 2-3 f bins, the arena as the bounds,
  ~2 s) intersected with the hero envelopes. Measure the needed lengths: for every HP loss in the recordings, how many
  frames before the hit the last safe exit vanished (SP14: 23-45 f, p50 ~40).
- Hysteresis: keep the chosen plan while its re-rolled key points stay inside the window's tolerance (the G-line
  flicker of 10-12 / 13: templates #29 / #60 / #43 rotating every 1-3 f); a key-change penalty is allowed.
- Speed: the per-frame part p99 <= ~10 ms; the long search in the background between branch points; a time cap with
  the fallback to the committed plan (if its check still passes) or the current planner.
- Strategy (named rules stay): the focus / switch / herding, the facing-to-the-wall value, the wall distance.
- Uncertain mechanics flag: a plan relying on an untested mechanic (e.g. the side down slash's bounce) is marked
  "to verify" and goes to a forced trial before live use.

STORAGE: the move timelines + the window tables under knowledge/1.0.30000/<enemy>/ (npz); the combo library one JSON
per combo (anchor event, preconditions as ranges, steps with timing windows relative to the anchor or to her own events,
branch points, status candidate / verified / promoted / demoted, evidence, an optional Chinese name); every executed
plan logged in the decisions in the same step format (for combo mining later).

## 2. Stages (sequential; each with fixed points / checks and a cause audit; switches default off, bit-identical off)

- M0 calibrations (live probes on w7, forced setups): the Deflate delay (attack / Clawline from the float), the float
  drift, the Clawline straight from the float, the side down slash's bounce, the down slash cadence after a pogo and
  after a whiff, the air dash after a pogo, the Idle hook reaction timing (12-18 f: why), the hold height vs her vy at
  the Clawline press, a second Clawline at control, the UNHOOKED Clawline's distance / time / height; the hero model updated (switch), facts in forum.md.
- M1 L2 envelopes (offline): the engine, validated against kinematics rollouts (every rollout inside the envelope,
  tightness reported), timings.
- M2 L1 Clapper model (offline): frame-accurate polygon timelines + the reaction rules + predict(); validation on the
  recordings; the overlay prepared for the person's eye check (do not use it live before the check).
- M3 L3 search + the acceptance suite (offline): situations for P1-P5 and the regression moves from the recordings
  (and forced setups), the found / not found table with reasons.
- M4 live (after the person's eye check): SSBOT_FORUM_MAP2 behind a switch, fixed points >= 90 % on P1-P5 and the
  regression situations, then the w7 A/B (hitless; the air show) and the w13 A/B, the audit.
