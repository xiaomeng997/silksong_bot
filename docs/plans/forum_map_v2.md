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
  SNAP A3's ORIGIN HEIGHTS (the person, 2026-10-21): yes - opens from any cluster at any frame create A3 origins at
  many heights, and the float moves slowly (0.005-0.1 u per frame), so nearby origins stay nearby for long: snap y0 to
  a coarser lattice (0.1-0.25 u) so they merge (~5x fewer A3 clusters). Two conditions: (1) a snapped cluster is a
  thin BAND (its height +- half a bin) in every danger check - conservative, still safe; (2) the chosen plan is
  re-verified with the exact unsnapped trajectory before it is committed (the tight strike windows need that). The
  same snapping may serve A1 / A2 in the far layer; x stays exact (interval sets).
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
