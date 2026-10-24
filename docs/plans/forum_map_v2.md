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
- The WALL PUSH of a jump (the person, 2026-10-22, from the recordings): near a wall the push acts late in the
  flight, near the landing (the flights that touch a wall last 43-47 f instead of 55); the RISE is unaffected - so a
  ride up is unaffected, but the landing x (and the jump cast's dome) must be predicted with the push.
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
- JUNCTIONS ONLY AT STEADY / CANONICAL STATES (the person, 2026-10-20 evening; it supersedes the lead's 'vy bins,
  hundreds of tables'): a continuation may start only from a state that is fully given by the position (plus a flag
  or two): standing on the ground (vx is instant), the apex of a jump / pogo bounce / Clawline bounce (vy 0, the
  umbrella closed), the float at its terminal -6 u/s, (later: the wall cling). Transitional states (jump frame 2, 3,
  ... 20, a bounce's rise, the umbrella's opening) never start a table: they live INSIDE a segment that starts at a
  steady state, and that state's forward table already holds every frame of every jump / hold / drift / umbrella
  choice in the segment. So the tables are a handful (ground, apex, float; x the dash flag), not one per transitional
  frame. This matches the person's 10-14 / 10-15 notes (the air by events: from a decision point straight to the
  apex; vertical only float / normal). The flags kept: the dash available, the attack cooldown.
- THE TABLE SET (the person, 2026-10-20, revised): the ground dash is unlimited, so the ground has two steady states,
  WALK and RUN (the sprint, 17.5 u/s, after a dash; accel 1.1 / step, the skid if released after Sprint Grace).
  START states: ground walk, ground run, air at rest (an apex), air float (its terminal -6 u/s); air normal at its
  terminal fall (max fall 30 u/s, reached after 0.5 s / 7.5 u from rest - possible in a full-height fall of the
  ~12 u arena; the lead's earlier 'never reached' used the anklet's 38 u/s). END conditions: the
  strike windows (can slash / can down slash / can Clawline) and the steady states WITHOUT the apex (ground walk,
  ground run, the float); 'air dash used' is a flag for the air only (the ground dash is unlimited). The
  APEX is never an end condition: after a strike, a separate STRIKE MODULE (the side slash's recoil, the pogo
  bounce, the Clawline's control and bounce) produces the next steady state (an apex or the ground) with its time and
  position, and that state starts the next search. Note: the float reaches -6 u/s only ~1 s after the Inflate
  (0.13 u/s per physics step from +0.5), so most float segments end before it.
- AIR START STATES (the person, 2026-10-20: 'vy = 0, the first controllable frame after a down slash, the first
  steady frame of the umbrella?'): yes, three canonical air starts, each fully given by the position + a few flags:
  (A1) AT REST, vy 0, umbrella closed: an apex, the end of an air dash (vy 0), the end of a hit recoil (v 0 after
  0.2 s); flag: the air hang available (only after a jump held through the apex, not after a bounce).
  (A2) THE BOUNCE, its first controllable frame (vy +17.4 in the 5-frame constant phase): after a pogo contact (the
  i-frames running, the attack ready ~19 f after the press) or the Clawline's control (no i-frames, the attack 9 f
  later) - the same curve, other flags; the whole rise and the apex are inside A2's table (the umbrella from contact
  +3 cuts the rise to +0.5), so a bounce needs no separate apex start.
  (A3) THE FLOAT's first steady frame (the Inflate's end, vy +0.5, then the float toward -6): vx from the antic's
  strong accel (8.5) is close to the held direction's float speed - 3 values (left / none / right).
  A3 IS A CURVE, NOT A CONSTANT (the person asked 2026-10-21 'does A3 still need to be dynamic?'): yes, like A1 -
  the float's vy goes from +0.5 toward -6 at 0.13 u/s per physics step, ~60 f to reach it, and most floats end before
  that (the air show: the float's vy p50 -1.3, its runs p50 10 f / p90 38 f). Its vertical is deterministic (no
  control but the close), so A3 clusters are keyed by their origin exactly as A1's, the steady -6 u/s is only the
  curve's tail. The one extra is the horizontal inertia: the x reach per frame comes from a small precomputed 1-D
  table per entry vx class (left / none / right), the Umbrella Turn included (a reversal takes its own clip, p50 19 f).
  Only A4 (the terminal fall) has a truly constant vy.
  NO SNAPPING (the person, 2026-10-21, final): the precomputed tables are computed exactly offline, and online the
  pass starts from her ONE exact observed state, so every derived cluster is exact too (snapping was only a way to
  merge clusters, not to model uncertainty). The online count is the raw number of event spawns from that one start -
  a few hundred to a few thousand, milliseconds compiled - so nothing is snapped. (The person's own earlier
  snapping idea of the same day, which the lead had adopted, is dropped by the person.)
  Common flags: the air dash used, the attack cooldown left. With the ground walk / run and A4 (below) 6 start states.
  TABLES CHAIN AT CANONICAL STATES (the person, 2026-10-20: 'if nothing happens in A2 before the apex, switch to
  A1?' - yes): A2's do-nothing branch IS an A1 state at the apex (vy 0, umbrella closed, no hang, the i-frames over,
  the attack ready) - so A2's table only covers the rise (~22 / 23 f: two variants for the 50 Hz / 60 fps jitter) and
  hands over to A1; an umbrella opened in the rise hands over to A3 at its steady frame, a dash to A1 at its end.
  Likewise A1's plain fall reaches the terminal -30 u/s after 30 f (7.5 u) - a canonical A4 (terminal fall). Every
  table is short; long reach = tables chained at canonical states (time-shifted, translated).
  JOINING A CURVE AT A PHASE (the person, 2026-10-20: 'A3 closed -> A1? not from 0'): right - the close is a Deflate
  carve-out (~6-7 f; measured: normal gravity, vy falls 1.2 u/s per physics step from the float's vy, no re-open for
  >= 13 f, an attack waits), after which she is in a plain fall at vy = (the float's vy at the close, +0.5 .. -6) -
  that is a point ON A1's fall curve, so she joins A1's table at the phase where A1 has the same vy (about frame 7-13
  of A1), shifted in time and position. Tables are therefore indexed by phase, not only entered at frame 0. M0: the
  horizontal control during the Deflate (the float's inertia or the instant run).
  FRAGMENTS AND HOW TO USE THEM (the person, 2026-10-20): the air dash does not widen the x interval - she cannot
  come back within the same time, so the x set splits into lobes with a hole (interval SETS handle it), and after the
  dash she is A1 at rest (good). A1 / A2 carry vy (one curve: A2 the rise, A1 the fall after the apex - its phase IS
  vy); A3 is a curve too (see A3 above); only A4 has a fixed vy. From A1, after 30 f she may be on A1 at phase 1, 2, ... 30 (different dash / close
  timings), each with its own height and x range - fragmented but cheap (tens to a few hundred fragments). Use: (1)
  'where can she be at frame T' and every danger / terrain check need only the PROJECTION onto (x, y): one region per
  frame, the union; (2) vy is an ATTRIBUTE of a point (the vy range available there), used only when continuing from
  it or timing a strike - not separate tables; (3) the coarse far layer bins vy coarsely (over-approximating).
  DANGER CUTS X ONLY (the person, 2026-10-20: 'a touch still needs a branch; with vy flattened how do you branch, and
  without flattening it is even more fragmented?'): danger never changes her vy - it only removes x (and kills a
  piece whose x is all gone). So a touch is NOT a vertical branch: it splits / shrinks the x interval sets of the
  pieces it touches. Vertical pieces are created only by EVENTS (the dash, the umbrella open / close, the Clawline,
  a pogo), few per airtime because of the locks. Keep each piece as a FAMILY over its event time (e.g. 'dashed at
  any frame in [d1, d2]' is one piece; at frame T its heights / phases form a curve segment); a danger cut may split
  the event-time interval into sub-intervals - the only branching, bounded. Waypoints / continuations only at the
  canonical states the families flow into (A1 at rest = an apex or a dash end, A3, A4, the ground), with the reused
  tables. The (x, y) projection is for the queries and the display only; the computation keeps the curves and phases.
  THE CLUSTER, EXACTLY (the person, 2026-10-21): a cluster is one vertical trajectory = (the curve, its ORIGIN TIME
  t0 = game frame - phase, its ORIGIN HEIGHT y0, the flags: dash used, umbrella locks, attack cooldown). Game frame 10
  at A1 phase 5 and game frame 11 at A1 phase 6 are the same cluster 'A1 phase 0 at frame 5'. Its vertical evolution
  is fixed, so it stores only the x interval set per frame. A cluster joined mid-curve (e.g. after an umbrella close,
  at A1 phase 5 on frame 10) is empty before the join (a virtual origin) and starts with the joining piece's x range.
  Clusters with the same key MERGE their x sets (quantised t0 / y0 make merges happen). Each frame an event can spawn
  a new cluster (a dash from a cluster that has not dashed -> an A1 cluster at the dash's end; a close -> A1 at a
  phase; an open -> A3; a pogo / a hooked Clawline -> A2), so roughly one new cluster per frame per event kind, but
  the flags and locks stop the cascade (a dashed cluster cannot dash again): about a hundred alive at most. A cluster
  EXITS when its x set is empty (cut by danger) or when it hands over (a landing -> a ground cluster, the terminal
  fall -> A4). Grouping adjacent clusters by event time is only an optional storage compression.
  HOW MANY (the person, 2026-10-21: '60 f in the air, a new height every frame, x the dash flag -> 3600 clusters?'):
  that order is right for the worst case (a dash at any of 60 frames, opens / closes at any allowed frame: a few
  thousand keys alive), and it is affordable: per cluster per frame one interval-set update plus one cut against the
  danger's x slice at the cluster's own height (precompute per frame the danger's x intervals per height bin) -
  ~3600 x 60 ~ 2e5 cheap operations, milliseconds compiled. Usually far fewer: clusters die when cut or landing,
  hand over to A4 / the ground, merge after quantising t0 / y0 (0.05 u; 0.25 u in the coarse far layer), drop when
  dominated (same curve and phase, the same height bin, a subset x set), and the backward pass from the goal windows
  keeps only clusters that can still reach one. M1 measures the real counts and times.
  IT SATURATES (the person: '120 f in the air -> 14400?'): no - the count does not grow with time without bound. At a
  given frame a cluster is (the curve, its phase, the height bin, the flags); heights are bounded by the arena (~12 u
  -> ~240 bins at 0.05 u), the phases by the curves (A1 ~31 until the terminal, the float ~50 until -6, A2 ~23, A4 1),
  so at most ~(31 + 50 + 23 + 1) x 240 x 2 flags ~ 5e4 keys per frame at 0.05 u whatever the horizon, far fewer
  reachable (a fast fall high up is impossible); the coarse far layer (0.25 u, vy bins) caps it near ~1e3. Staying up
  120 f at all needs the float or bounces (an unbraked fall from 12 u lands in ~38 f).
  THE COLLAPSE AND THE RECURSION (the person, 2026-10-21: 'when time passes my cluster's x becomes a point and its
  future a cone - the derived clusters cannot be collapsed; tables for A1 collapsed at every phase, each with all
  derived transformations for 120 f? that is recursive - compute it explicitly or find a recursive element?'):
  - It is recursive but CLOSED over a finite set: the start states (curve, phase, flags) - A1 ~31 phases, A2 ~23,
    A3 ~60 x 3 vx classes, A4, ground walk / run - a couple of hundred. Everything is relative to her position
    (translation invariance), so x never enters a table key.
  - THE RECURSIVE ELEMENT = the one-step transition table: for each start state, 'continue' -> (curve, phase + 1),
    and every allowed event -> its resulting start state + its displacement (the dash +-2.8 u, the Clawline's pull)
    + its duration. From it, R(s, t) for every s is computed EXPLICITLY offline by dynamic programming over t
    (R(s, t) = s's own motion u the events' children R(s', t - tau) translated) - no symbolic machinery needed.
  - Store per start state and frame only the UNION region (a relative polygon / interval set; optionally the
    earliest-touch data), not the per-cluster detail: ~200 states x 120 f x a small polygon = a few MB.
  - THE COLLAPSE IS FREE: every tick her exact state (curve, phase, flags) picks a table, translated to her exact x /
    y - old clusters are never 'collapsed', they are rebuilt. Online, with danger, the cluster forward pass starts
    from the exact current state with the transition table and the cuts (ms), rebuilt at every branch point.
  - Longer horizons compose: R(s, t1 + t2) from R(s, t1)'s canonical end states and R(s', t2) (the coarse far layer).
  - CAUSAL, NO CIRCULAR REFERENCE (the person asked): R(s, t) uses only R(., t') with t' < t because every event
    takes >= 1 step (the dash 0.1 s, the umbrella >= 17 f open + ~7 f close, a re-open >= 13 f after a close, the
    Clawline 26-34 f). The STATE GRAPH has cycles (A1 -dash-> A1, A1 -open-> A3 -close-> A1, A2 -> A1), but each
    cycle consumes time, so unrolled in time it is a DAG: compute by increasing t. Two rules keep it clean: (1)
    zero-time relabels are ALIASES, not edges (A2 at its apex IS A1 phase 0; A1 at the terminal IS A4) - one
    canonical name each, no self-loops; (2) count time in 50 Hz physics steps inside the tables (exactly causal;
    some 60 fps frames have no step) and convert at the interface. The flags break some cycles anyway (one air dash).
  - THE GROUND TABLE (the person, 2026-10-21): in the air the state at any moment is fixed, so its reach map is one
    table; on the ground the take-off time tau and place are free - the ground table is the UNION over tau of the
    jump tables DILATED by the walk interval reached by tau (a Minkowski sum / max-plus convolution), plus the
    stay-on-the-ground part - again one deterministic table per ground start (walk, run). Because left / right is
    decoupled and the air speed equals the walk speed, it is close to 'x in [-X(t), X(t)] x y in [0, the running
    max of the jump height]', with corners where the sprint / dash couple. Like every table it holds only the union;
    the per-take-off arcs for the danger cuts are regenerated online from the transition table.
  - WHICH TABLE (the person: 'in the air the state picks one of ~200 maps'): yes - the key is (the curve, its
    phase, the air-dash-used flag, the float's vx class): A1 ~31 + A2 ~23 + A3 ~60 x 3 + A4 1 ~ 235 x 2 for the dash
    flag ~ 470 air tables, plus ground walk / run - each a small polygon per step, a few MB in all. NOT keys (they do
    not change where she can be): the attack cooldown (a time mask on the 'can slash' flag) and the pogo i-frames (no
    cuts while they run) - handled online. Short locks (no re-open for 13 f after a close) may be over-approximated in
    the free-space table and enforced exactly in the online pass and the final re-verification.
  - THE CLAWLINE IS AN EDGE, NOT A KEY (the person, 2026-10-21): the air tables include the UNHOOKED Clawline as a
    movement event from every air state where it is allowed, left or right (she turns instantly): the antic hover
    (~8-9 f, the height held, ~1.2 u drift toward the facing), the flat pull (~5.7-7.8 u, 70 u/s), and its end maps to
    an EXISTING state (A1 at rest if it ends with vy 0, A2 if it ends in a bounce - M0 says which). No 'Clawline used'
    or cooldown key (silk is not a constraint); if M0 finds a cooldown it is a short lock like the umbrella's re-open
    (over-approximated in the table, exact online). The hooked Clawline stays online (it depends on the target).
    THE CLAWLINE'S COOLDOWN AS A KEY? (the person asked): decide on M0's number - if the next Clawline is free at
    its control (only the 26-34 f block), no key; if a cooldown outlasts the block, add a 'Clawline ready' flag like the
    air dash's (x2 air tables, ~940, still a few MB) - a cooldown that changes where she can be belongs in the key;
    only a very short one may stay an online lock.
- THE AIR: HORIZONTAL INTERVALS x DISCRETE VERTICAL CURVES (the person, 2026-10-20): left / right can go back and
  forth, so an x interval per frame is right; but the fall is one-way and only a few events change vy, each to a
  fixed value and with its own lock: the umbrella (Antic 6 f at gravity, then Inflate vy +0.5 for 12 f, then the
  float toward -6; no close before 17 f; a re-open >= 13 f after a close), the air dash (vy 0 for 0.1 s; one per
  airtime - is it restored by a pogo? M0), the Clawline (the hold, then the bounce +17.4 or a flat unhooked pull), the
  pogo (+17.4, 5 f constant then gravity), the jump's release frame on the take-off, and the AIR HANG
  (kinematics.py: holding jump through the apex sets the gravity scale to 0.1 at the first falling step, +0.1 per
  step while held, back to 1 on release - a slower start of the fall; a hold-time parameter). Otherwise the fall is
  free fall: g 60 u/s^2 (1.2 u/s per 50 Hz physics step), capped at 30 u/s. So the vertical state is a
  small DISCRETE family: canonical curves y(k), vy(k) (the fall from rest, the float after the Inflate, the bounce,
  the fall after a Deflate, the jump per release frame) glued at event frames. Store those curves as 1-D arrays (no
  2-D air tables); at use time build the event tree (event frames on a 2-4 f grid, refined near tight windows; the
  locks and the one air dash prune it; target-dependent events - a pogo, a hooked Clawline - come from the strike
  module), each branch = one vertical curve with the horizontal interval of its mode = one horizontal segment per
  frame, checked against the danger polygons and the terrain. Tens to a few hundred branches per airtime. The 2-D
  'air envelope' is only their union (for display); the ground keeps its interval tables (y fixed until the take-off).
- NO ENUMERATION OF EVENT ORDERS: PROPAGATE STATES AND MERGE (the person asked 2026-10-20: dash-then-umbrella vs
  umbrella-then-dash vs two umbrella cycles vs a Clawline left then right, and how 20 free frames split between them,
  explode combinatorially; the dash and the Clawline move x, the float slows x with inertia). Answer: a frame-by-frame
  forward pass over STATES, not sequences. A state key = (the vertical curve and its phase, the height quantised to
  ~0.05 u, the locks / flags: umbrella open / opening k / closing k / reopen lock, the air dash used, the Clawline
  block phase); its value = the reachable x as a set of intervals (+ vx bounds inside the float). Each frame every
  state either continues (x intervals widen by the mode's reach, the float by its bounded accel) or starts any allowed
  event (the dash: x +-2.8 u, height held; the unhooked Clawline: the flat pull; the umbrella open / close) -> a new
  key. Equal keys MERGE (their interval sets unite) - different orders that end in the same state cost nothing extra;
  dominated states (same key, a subset of x) are dropped; danger and terrain cut the intervals at that frame. The
  vertical's discreteness keeps the keys few: heights <= arena / 0.05 ~ 250, x a handful of modes x a few flags -
  at most a few thousand keys per frame, usually far fewer; 60 frames is well within a compiled pass. A backward pass
  from the goal windows (meet in the middle) prunes further; the free-space results from the canonical starts are the
  precomputed tables. Event-time grids are not needed: every frame is a possible event start, the merging absorbs it.
- TERRAIN CONTACTS ARE BRANCH EVENTS, NOT END STATES (the person, 2026-10-20): the tables are terrain-free; the system
  must handle scenes with terrain, and a landing height need not equal the take-off height. Where the envelope's
  lower boundary first touches a floor / platform top, that contact generates a branch: those positions at that frame
  become a GROUND WALK start at the floor's height, and the ground table continues from there (per contact x its
  earliest frame). Walls (cling / slide) and ceilings (a bonk resets vy) are contact events of the same kind.
  STORAGE = CONTOUR VERTICES (the person): one polygon (or a union of a few) per (start state, end condition,
  frame). Because horizontal and vertical are decoupled (instant run; the jump hold, the fall and the umbrella act on
  y only), each region is close to a product 'x interval x y interval' - nearly a rectangle - with a few cut corners
  where they couple (an air dash holds the height; the float's horizontal inertia gives the float pieces their own
  x range; the Clawline). So a frame needs only a handful of vertices: 40 x 120 frames is a few MB at most.
  Intersections with the danger polygons are polygon tests (convex pieces, SAT); forward ∩ backward is a polygon
  intersection; grids are only rasterised on the fly (the coarse far layer, debugging), not stored. Left-right
  mirror symmetry halves the set; the vertical extent is clipped to the arena.
- Danger inside one segment (between two steady states): roll that segment's small family on the fly (take-off frame
  x jump hold x drift pattern x umbrella timing x Clawline / dash press) against the predicted danger - no stored
  transitional tables. Meet in the middle likewise joins only at steady states (e.g. 'standing at frame 8'), and the
  backward tables are keyed by steady goal states or by window events.
- Use: the search runs inside the envelope until the first frame it touches any predicted damage box or terrain -
  that frame IS the branch time (generated automatically); until then every point inside is free. To go on, pick a
  waypoint inside the envelope at the branch time (a position in a STEADY state - see the junction rule; several
  candidates, a small tree) and restart from the reused table of that state. Paths to a chosen point are cheap (instant run: hold
  toward it m frames, then release).
- A fixed future time T: as she moves, the envelope for T shrinks (the future collapses into the past). Use it as the
  commitment monitor: a planned target at T stays valid while it is inside the shrinking envelope (the hysteresis).
- Where dangers interleave inside one segment (weaving between two boxes), the frame-by-frame propagation with the
  danger subtracted complements the waypoint restarts.

MEET IN THE MIDDLE (the person, 2026-10-20 evening): branches can be computed backward. A goal at a later time
(e.g. a window's press region at frame 20) has a BACKWARD envelope: the states from which it is reachable in n
frames. Forward 10 frames from her (danger subtracted) intersected with backward 10 frames from the goal (danger
subtracted) at frame 10: any overlap at a STEADY junction state (standing, an apex, the float; the dash flag) is a path
around the obstacle; the junction is picked inside the overlap (the most margin), the keys come from both
halves' witness paths. Horizontal is time-symmetric (instant run) but vertical is not (gravity), so the backward
tables are precomputed separately, keyed by the arrival state. Per frame, forward ∩ backward is the tube of all
feasible paths: the robust choice and the commitment monitor. The search then asks per window 'forward ∩ backward
non-empty?' instead of branching at every touch.

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

HOW TO GET THERE (the person, 2026-10-22: 'the map says which points are reachable but not how - is the exact
computation picking a point and choosing keys, or are the keys stored for every point?'): neither store-everything nor
blind choice:
- BACK-POINTERS LIVE ON FULL STATES, NEVER ON THE FLATTENED MAP (the person, 2026-10-22: a projected cell can be
  reached in several full states - very different vy / vx / keys pressed; with one pointer per projected cell C may
  point to B while B points to A', and from A' the state at B cannot reach C). The flattened region is only for the
  queries (reachable at all? the first touch?). Paths come from the CLUSTERS: a cluster is one vertical history, so
  its parent cluster and its event frame are unique; B-via-A and B-via-A' are different clusters even where they
  share (x, y). Offline, keep the cluster tree of every start state (clusters with parent, event frame, the x
  interval sets per step - finite, tens of MB in all); online the cluster pass builds the same tree with the cuts.
- Reconstruction: the clusters whose height at t is the target's y and whose x set holds its x; walk their chain
  back for the vertical events (the dash at d, the umbrella at u / the close at c, the jump release r); inside each
  cluster rebuild x backward - with the instant run always possible (x(t-1) = the clamp of x(t) into the previous
  interval within one step, it exists by construction of the dilation); inside the float (vx inertia) solve the
  bounded-acceleration switch times (a bang-bang path to any interior point exists).
- A CLUSTER = (ITS TYPE, ITS SPACE-TIME ORIGIN); A PATH = THE EVENT LIST (the person, 2026-10-22): a cluster's free
  evolution is its type's table translated to its origin (the fixed vertical curve, the shared x growth), so free
  clusters store nothing per frame - only the danger-cut ones carry their cut x sets. A path is the list of non-left /
  right key events (jump press / release, dash, umbrella open / close, Clawline, attacks) with their time and place;
  left / right between them is rebuilt. 'An event gives the same state whatever came before' holds for the TYPE of
  most events (dash -> A1 at rest; a pogo -> the 3.74 u bounce; a hooked Clawline's control -> the 4.09 u bounce; the
  open -> A3 after the Inflate with vx by the held key; a landing -> ground walk), but NOT always for the ORIGIN: the
  umbrella antic falls 6 f from the prior vy; the Clawline's hold height depends on vy at the press (+0.074..0.080 x
  the clamped vy); the close continues the float's vy (A1 at the phase with that vy) and freezes vx for 6 f; the
  unhooked Clawline ends at A1 with a residual vx 12.46 decaying x0.923 per step. So an event is a deterministic map
  'prior state at the event frame -> (type, origin)', computed exactly; the new cluster then runs on its type's table.
- 'Exact computation' then means: simulate THAT concrete key string with the exact hero model (HERO2) and check it
  frame by frame against the predicted danger polygons (with their margins) before committing - the tables say what
  is possible, the simulation confirms the chosen path.

BOUNDS (the lead's proposal, 2026-10-22, asked by the person; M3 checks them on the data):
- TIME: the precomputed tables and the standard horizon 2 s = 120 frames = 100 physics steps (it covers a jump
  cast from its Jump Aim to the end of the burst, 55 + 65 + ~8 = ~128 f, and the trap lead times, 23-45 f before a
  hit); the exact online part only to the candidate's next branch point (typically 10-40 f); the coarse exit check
  stretched to 3 s (180 f) only while a jump cast is in its antic (antic 55 f + the rest); beyond the horizon the
  terminal value. The enemy predictions use the same horizon, with at most two future enemy choices branched.
- SPACE: the arena itself - the Forum walls x 14.01 .. 48.99 (35 u), the floor y 3.015 to the ceiling step ~15.15
  (~12 u). The relative tables span x +-35 u (2 s of sprint + dashes / Clawlines can cross the whole arena) and y
  -12.2 .. +9 u (the floor below, the jumps and bounces above, the ceiling caps it); walls / floor / ceiling are
  applied at use time as terrain events. Other rooms: their own bounds from the terrain map.

STEADY-STATE TABLES + ACTION LISTS (the person, 2026-10-22 evening, after M1's numbers: 1,758 start-state tables,
30 f horizon, 23,831 exact clusters in 16 f from rest - the air dash cancellable on every frame): open a table ONLY at
a steady state (ground walk, ground run, air at rest, the float steady, the terminal fall - a handful, not 1,758);
between two steady states the discrete events follow ONE action list from a fixed library (e.g. ~2000 lists: the
dash / air sprint and its length, the jump hold, the umbrella open / close frames, the Clawline - whatever is
needed), chosen at the steady state and not changed during the transition; left / right stays free every frame (an
x interval, the instant run). Each list = one vertical curve + its x reach, so a table = the union over its lists,
and tables chain at steady states to any horizon (120 f and more - not 30). Cost of the restriction: no new discrete
decision in the middle of a transition (a jump, a dash, an umbrella opening); safety still holds by the reveal rule
(a list must be safe for every enemy outcome until the next steady state, with left / right steering after the
reveal); the loss is some adaptivity in fast exchanges - keep a small set of EMERGENCY deviations (dash / umbrella /
Clawline from mid-transition) for model errors. DEFERRED (the person, 2026-10-22: 'not fully thought through yet;
if the tables already built work, use them for now'): M3 / M4 use M1's tables as they are; revisit this scheme (and the
natural selection below) after M4's live results (M3 already chains <= 2-event segments at canonical junctions);
made concrete by the person on 2026-10-23: THE A1_n RECURSIVE TABLES below.
TABLE KEYS UNDER THIS SCHEME (the person, 2026-10-22): the fall keeps one table per frame of the fall from rest (each
vy until the terminal speed: ~30) + the terminal fall; the float one per frame of its curve (~60) x a few vx bins (its
inertia); ground walk and run - about 200 in all, x 2 for 'air dash used' in the air. The DASH AND THE JUMP DO NOT
MULTIPLY THE TABLES: they are items of the action lists / edges whose results land in these same tables (the jump
from the ground ends in the fall curve at a phase; the air dash + air sprint ends falling at some vy = the fall table
of that phase; the bounce and the Clawline end at an apex = fall phase 0). Their timing and length are parameters
of the list item, not keys.
NATURAL SELECTION OF THE ACTION LISTS (the person, 2026-10-22): the action space may be huge; a list SURVIVES only if
it reaches some space-time point with FEWER actions (key presses / events) than every other list - otherwise it is
eliminated. In the offline build, per reachable (point, ARRIVAL STATE) keep the list with the fewest presses (ties:
the earlier arrival, then the more options kept - the air dash unused, the attack ready sooner; NOT a clearance:
the build has no danger yet, the person 2026-10-22 - danger-aware choices are made online); the back-pointers are the survivors, so a reconstructed path is the
simplest one (fewer presses = fewer timing errors; the old key-change penalty was the same idea). Two cautions: (1)
compare only lists that arrive in the SAME state (vy, flags), not just the same point (the A -> B -> C lesson);
(2) keep a few DIVERSE survivors per endpoint (different routes: under / over / a different height on the way),
because online danger can cut the simplest one - the online cluster pass with every event stays the fallback. M1b
reports how many lists of the library survive.
THE A1_n RECURSIVE TABLES (the person, 2026-10-23 morning; agreed with the lead's points 1-6 below; BUILD AFTER M4's
GATE RESULT - and if M4b cannot reach live speed, this is the next step). The person's design, for the free fall:
- A1_n = the free-fall table whose space-time origin has the vertical velocity of n steps of falling from rest
  (A1_0: at rest, A1_1: one step of fall, ...). x, y, t are relative to the origin.
- NO REDUNDANCY: A1_0 = A1_1 referenced one step later (moved by the fall of that step, its left / right envelope
  widened by one step) + ONLY what the actions pressed at frame 0 add - nothing else. A dash pressed at frame 10 is
  NOT in A1_0: it sits in A1_10, reached through the chain A1_0 -> A1_1 -> ... -> A1_10, each link widening the x
  reach by one step. Exact: the normal fall's run is instant and has no memory (8.25 u/s = 0.165 u per step).
- Frame 0's actions: the dash with its hold lengths, the Clawline, the umbrella (the person's estimate ~1000; see 5).
  A pressed action leaves a space-time trajectory (an x interval per step, left / right free) kept in THIS table
  until it reaches a steady state, labelled per step: LOCKED (can be hit, cannot attack), TRANSITIONAL (can be hit,
  can attack), INVINCIBLE (cannot be hit, cannot attack - 'as if she were not on the field', but see 4). At the
  steady state the table stores the endpoint (its relative position interval and time), the REFERENCE (which table
  to insert at that point) and the action id it came by. An action always starts at the origin.
- Why it fixes M1's count: M1's 23,831 exact clusters in 16 f from rest (286 without the air dash) are mostly the
  air dash pressed at each frame 0..15 times its cancel variants (rough: ~1,500 per start frame), all carried in one
  forward set; here each sits once in its own A1_n, so the storage does not grow with the horizon (120 f and more).
- The air dash ends exactly on the lattice, no snapping: M4a measured that the dash zeroes vy every step and gravity
  then acts in the step, so vy in the air sprint runs -1.2, -2.4, ... per step like the fall from rest. To check: the
  air sprint's eased fall clamp (-10 -> -30 u/s over 1 s) may bite at the end of a long sprint.
- THE AIR DASH GOES ONE WAY INSIDE THE TABLES (the person, 2026-10-23): it is used once per airborne stretch and
  nothing inside the tables restores it (the unhooked Clawline and the umbrella keep the flag - M4a; only a landing,
  a pogo hit or a hooked Clawline restore it, and those are use-time events). So every table needs its NO-DASH
  version, and once the dash is used every later recursive element is a no-dash one. The no-dash tables are SMALL:
  M1 counted 286 exact clusters in 16 f from rest without the air dash vs 23,831 with it; frame 0's actions there are
  only the Clawline L / R, the umbrella (with its close timings) and nothing.
- ONE SHARED DASH BUNDLE (follows from the above and M4a): the dash zeroes vy every step, so its whole family
  (direction x hold length x cancel x cancel frame, ~1000 trajectories) is the SAME from every A1_n - it depends only
  on the physics-step phase of the press frame and on the jump being held. Store it ONCE per phase; its endpoints
  reference no-dash tables. (Superseded by the next two bullets: there are no dash-version tables.)
- THE AIR DASH IS NOT IN THE TABLES (the person, 2026-10-23): the bundle is an independent module used ONLY as the
  bridge between the forward and the backward no-dash sets (next bullet). Every table is a no-dash table; 'the air
  dash used' is no table key but a property of the segment between two refills (known at the segment's start; the
  bridge is allowed only if the dash is unused there); the tables carry per frame only whether a dash PRESS is
  allowed (airborne, no lock such as the umbrella's antic). The bundle's endpoints include its cancels' outcomes (the
  jump cancel into the umbrella = an A3 entry by vx; the Clawline out of the sprint = a hook (a refill) or an unhooked
  Clawline transient; the attack cancel with its extra air velocity) and land in no-dash tables. THE GROUND DASH IS
  IN THE GROUND TABLES (the person, 2026-10-23 ~20:15: 'the ground should do the dash; after a ground sprint jump she
  can still air-dash' - this replaces the lead's short-lived 'ground dash as a bridge' of the same evening): the
  ground dash and the air dash are different resources - a ground dash does not use the air dash (M4a: after a ground
  dash and a jump the air dash fires 4 frames after the jump, 27 / 27; the sprint jump sets the dash cooldown to 0.1
  s). So the ground tables hold walk / run, the ground dash (3.5 - 4.05 u, the next press >= 25 f later), the ground
  sprint it leads into (17.5 u/s) and the jumps out of it - the SPRINT (shuttlecock) jump: the sprint FSM's Jump
  Antic ~6 f, then vx 18 u/s fixed while rising, jumped_steps -5 - and the sprint's dash attack (the Wanderer lunge);
  leaving the ground starts an air segment with its one air-dash bridge available. GAP: the shuttlecock jump and the
  dash attack are not in kin_jit yet (M4a: 25 + 3 trials, 1.5 - 8 u off; the envelope does not offer them) - model
  them from M4a's trials before they go into the ground tables.
- MEET IN THE MIDDLE, THE DASH BUNDLE AS THE BRIDGE (the person, 2026-10-23): between two refills a path has at
  most one air dash, so every path is no-dash -> (at most one dash) -> no-dash. Push the small no-dash tables FORWARD
  from her state and BACKWARD from the goal (the next strike window's press region: the down slash on a body, the
  hooked Clawline's reach; or a safe endpoint), and join them with the dash bundle where the gap matches: a dash
  variant d (displacement dx_d - an interval, left / right are free in the sprint -, dy_d, duration T_d, end state
  e_d) bridges at t1 if F(t1) shifted by d meets B_e_d(t1 + T_d). Without a dash: F(t) meets B(t) directly. The dash
  ignores her vy at the press, so the forward side only needs WHERE and WHEN an air-dash press is allowed (airborne,
  the dash unused, no lock such as the umbrella's antic) - any vy. Conditions: the dash's own tube (~17 f) is cut by
  the danger too (the start x's whose tube stays clear = the intersection of each dash frame's danger-free set shifted
  back to the start); the backward tables are keyed by the dash's end states (the A1 lattice; the jump-held variants
  on their own chain); one bridge per segment between refills (a pogo, a hooked Clawline or a landing restores the
  dash, so the next segment may bridge again). Cost: interval shifts and intersections over ~120 start frames x the
  bundle's variants grouped by (dy, T, end state), instead of a forward set multiplied by every dash (M1's 23,831).
- FLATTENED AND CHAINED, BOTH (the person asked 2026-10-23 'chain the tables one by one, or one flattened
  version?'): keep a FLATTENED union per start state and frame (where she can be, not how; small whatever the cluster
  count - the dash's 23,831 clusters are a few x intervals per frame) AND the CHAINED tables. The flattened union is
  built without danger, so it is an UPPER BOUND: (1) prune - a strike window outside it is out of reach, skip it;
  (2) exact until the danger first touches it - before that frame use it as is. From that frame on CHAIN: step the
  tables frame by frame and cut each frame's danger (the flattened union cannot be cut: it does not know which point
  came from which). Reconstruct the keys only along the chain (the action ids of the references; back-pointers on
  clusters, never on the flattened maps - the A -> B -> C lesson).
- A REFERENCE CARRIES THE ENVELOPE'S WIDENING (the person, 2026-10-23): when a frame references the next one it
  carries the left / right growth, so a reference is (target table, dt, dy, an x OFFSET INTERVAL [lo, hi]), not a
  point; references compose by adding intervals ([lo1 + lo2, hi1 + hi2]); a table's trajectories (x intervals relative
  to its origin) seen through [a, b] become [x_lo + a, x_hi + b]. The data structure needs a WIDEN method (an x interval
  set, the state, the steps -> the widened set): A1 (the instant run, no memory) +-0.165 u per step each side, exact;
  A3 (the float's inertia) per its vx class - the low end follows the always-left lane, the high end the always-right
  lane (M1's lanes), the growth stored per frame of the float tables; the extra air velocity after a sprint cancel
  (x0.8 per step, one-sided) stays inside the transient's stored trajectory until it is spent. At use time: after a
  danger cut the set has holes - widen each piece and merge (still exact); walls are absolute - clip to the arena
  (x 14.01 .. 48.99) after every widening step, then go on widening (she can run along the wall or back).
- INTO AN INERTIA STATE THE REFERENCE SPLITS BY vx (the person, 2026-10-23: 'A1 whose next frame is a left, a
  middle and a right A3 cannot reference one 3-wide envelope like A1 - it references three times'): A1 has no
  horizontal memory, so one widened interval covers every key; the float's future depends on its vx, so entering it
  needs one reference per vx, each with its own x interval. M1 found THREE entry classes (left / none / right): the
  umbrella antic's strong accel (8.5 per step) brings vx near the held direction's float speed by the Inflate's end;
  check at build time that every key pattern of the antic gives a bit-equal vx per class - if not, one reference per
  distinct vx, or groups bounded by their always-left / always-right lanes (an over-approximation: a few extra
  candidates, rejected by the final exact simulation; nothing reachable is lost). Inside the float vx changes slowly
  (accel 1.0 / decel 0.25 per step, a full Umbrella Turn ~19 f): those in-between vx are covered by each class's lanes,
  not by more classes. The float's vy is one fixed curve (+0.5 at the Inflate's end, -0.13 u/s per physics step to -6
  in ~60 f; M1: phases 0 .. 58) - no vertical classes; so ~59 phases x 3 entry classes (x the physics-step phase).
  SUPERSEDED THE SAME DAY - THE FLOAT'S HORIZONTAL IS AN ENVELOPE TOO (the person, 2026-10-23: 'planned ahead she can
  reach any x in between closely enough'): always-left gives the leftmost lane, always-right the rightmost, and with
  planned key changes every x in between is reached closely enough, so the float's x reach per frame is the interval
  between the two lanes - an envelope like A1's, only its growth follows the lanes instead of a constant. The entry vx
  needs no classes either: the reference carries an x interval AND a vx interval; the low lane starts from (x_lo,
  vx_lo) holding left, the high lane from (x_hi, vx_hi) holding right. One float table per vertical phase (~59).
  Checks at build time: (1) monotonicity - a start further left / slower never reaches further right later -
  including the Umbrella Turn (~19 f) on a reversal; (2) the gaps - key changes are per frame, so the in-between x are
  dense discrete points: measure the largest gap, it must be well under a strike window's width; (3) the keys and the
  vx at a chosen x come from M1's horizontal tracker (the witness), and the final exact simulation confirms them.
  They MERGE BACK once the lanes saturate: after a few steps of a held key the lanes reach the float's max speed
  whatever the entry vx, so from then on every branch widens by the same constant per step (like A1, another speed)
  and the branches' intervals unite into one reference. The split lives only in that transient (an unspent 'timer',
  as for the steady-state rule).
Points to settle when building (the lead, 2026-10-23, the person agreed to record them):
1. STEADY = every hidden state that affects later actions equals the target table's origin. Wait out the timers (the
   0.1 s attack queue; the extra air velocity after a sprint cancel, x0.8 per step; the Clawline lock until control
   + 13; the umbrella re-open lock until release + 12). Flags that cannot be waited out become table keys: the air
   dash used (restored only by a landing, a pogo hit or a hooked Clawline - M4a) -> A1 x 2. [Superseded 2026-10-23:
   the air dash is not in the tables; 'used' is a segment property checked by the bridge - no x 2.]
2. The dash with the jump held is OFF the lattice (M4a: gravity 0.1 in the dash steps, vy +1.08 u/s for good, until
   a bounce or a landing): its own chain (the same recursion, the origin vy offset by 1.08) or not offered.
3. Time in 50 Hz physics steps inside the tables: some 60 fps frames have no step (seen in M4a's dash), so 'n frames
   of fall' does not fix vy. Convert at the interface (as the recursion paragraph above says).
4. INVINCIBLE segments keep their positions: the Clapper chooses from her position even while she is invincible
   (Close Range <= 8.05 u: slam / evade / cast; the Jump aim from her x; FaceObject), and walls / the ceiling / the
   floor change the endpoint. Positions only, labelled 'cannot be hit, cannot attack' - cheap.
5. The action count: the air sprint runs while the dash key is held (M4a: Air Sprint Loop, the regain with the key
   up) and every sprint frame allows the attack / jump / Clawline / dash cancels, so direction x hold length x
   cancel x cancel frame is over 1,000. Alternative with the same recursion: 'sprinting at step m' as its own chain
   (S_m = S_m+1 one step later + the release / cancels at m); frame 0's actions then shrink to a handful (dash L / R,
   Clawline L / R, umbrella, nothing). Both exact; the chain has more but tiny tables. Decide at build time.
6. Floor / walls / ceiling are absolute and the tables relative: cut at use time (the person: a landing is a branch
   where the envelope meets the ground, not a steady state).
Use: the search looks the tables up instead of rolling the physics per frame online (M4b's limit on 10-23: within
0.25 s the plans are worth 0.38 expected hits on the recorded w7 situations vs 1.9 for the 60 s search); a bounding
box per action (its trajectory + its endpoint table's reach) prunes the lookups. The same pattern applies to A2 (the
bounce), A3 (the float, keyed by vx) and the ground.

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

## 1b. Open questions and risks (the lead, 2026-10-20, after the design talk)

1. ACCEPTANCE WITHOUT LEAKS: 'found by the search' means primitives + the generic strike module only - the combo
   library must NOT contain P1-P5's own macros during the acceptance run (else it is trivially 'found'). Run the suite
   twice: primitives only (the real test) and with the library (the speed / quality comparison).
2. MARGINS FROM MEASURED ERRORS: every model (the hero curves, the enemy polygons and timings) carries its measured
   error; the checks grow the danger polygons / shift the timings by it (per move, per frame offset), and plans that
   lean on an untested mechanic are flagged. History: the air strike (1 / 5) and the special mode failed on model
   errors, not on search.
3. LATENCY IN THE COMMITMENTS: STATE arrives 1-2 f late, keys are sent 2 f ahead, the 50 Hz / 60 fps jitter, host
   stalls (late ticks ~0.4 %): the reveal frame + the reaction lag must be in every 'safe until she can react' check.
4. THE ENEMY'S CHOICE MEMORY: the Close / Far Range choices use V4 with eventMax / missedMax (no long repeats; after
   Evaded only SLAM / CAST; the escape jump alternates 1:1) - so the outcome probabilities depend on its recent
   choices; model the history, the search can exploit it.
5. TWO ENEMIES ARE A JOINT STATE: the buddy lock couples them; predict() must take both and branch jointly (outcomes
   multiply); keep it bounded (the locked one has no new move until the other's lock ends).
6. THE OBJECTIVE BEYOND THE HORIZON: hits per second and safety inside the horizon are not enough - a terminal value
   for the end state (room to the walls, its facing / wall distance, the other Clapper's position, still having a
   strike window next) or the search will take greedy paths into corners. forum_reach.npz's TerminalValue is the
   precursor; redesign it with the envelopes. Hitless first: a plan must be safe for every outcome; hits rank the safe.
7. WHAT CAN BE HIT AND HOW: per move and frame which polygons are pogo-able / tink / pass-through (the slam's hammer is
   passed through, the Slam 0 body is the strike), the enemy's own invulnerable states (the intro), her slash recoil
   and its push on the enemy (0.48 u per side slash) - all inside the strike module.
8. COVERAGE: unknown or rare enemy states (stuck at a wall, the wall push of a jump, the death) fall back to the old
   conservative supports; walls (cling / slide / wall jump) are not modelled yet.
9. MEASURING LIVE: one 64-episode A/B cannot see small gains (the same default gave 18 / 64 and 5 / 64); keep the
   default as a control in every session and pool.

## 2. Stages (sequential; each with fixed points / checks and a cause audit; switches default off, bit-identical off)

- M0 calibrations (live probes on w7, forced setups): the Deflate delay (attack / Clawline from the float), the float
  drift, the Clawline straight from the float, the side down slash's bounce, the down slash cadence after a pogo and
  after a whiff, the air dash after a pogo, the Idle hook reaction timing (12-18 f: why), the hold height vs her vy at
  the Clawline press, a second Clawline at control, the UNHOOKED Clawline's distance / time / height, the ground dash's cooldown (unlimited?) and the sprint's steady state; the hero model updated (switch), facts in forum.md.
- M1 L2 envelopes (offline): the engine, validated against kinematics rollouts (every rollout inside the envelope,
  tightness reported), timings.
- M2 L1 Clapper model (offline): frame-accurate polygon timelines + the reaction rules + predict(); validation on the
  recordings; the overlay prepared for the person's eye check (do not use it live before the check).
- M3 L3 search + the acceptance suite (offline): situations for P1-P5 and the regression moves from the recordings
  (and forced setups), the found / not found table with reasons.
- M4 live (after the person's eye check): SSBOT_FORUM_MAP2 behind a switch, fixed points >= 90 % on P1-P5 and the
  regression situations, then the w7 A/B (hitless; the air show) and the w13 A/B, the audit.
