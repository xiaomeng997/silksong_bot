# Forum zones v2: idle = body, group 1 = decided moves, group 2 = pending aims on group-1 terrain

2026-10-09 late evening, architect pass. Read-only: no repo edit, no commit, no game, no new measurement (weekly usage
was 66 % at the start of this pass, the stop line is 70 %, so everything below is built from the existing results).

Sources read: the person's rules in `docs/plans/forum_planner_plan.md` sec. 5 (main 4416860, "two groups"),
`C:/ssbot/data/m2_forum_cases/fix_spec.md` (sec. 2, 7-10 and addenda), `m2_forum_cases/zone_cases_result.json` (via
fix_spec), `m2_forum_aimics/workflow_result.json` (Reed pin), `m2_forum_aimics/spear/workflow_result.json` (Clawmaiden
spear, aim_ics.py at fc31849), `m2_forum_push/workflow_result.json` (S0-S5 and the verifier), the three classifier
results of this workflow (`m2_forum_v2/cls_reed_min_mae`, `cls_en_ch_cm`, `bell_clap`), and the planner / support code
in the frozen checkout `C:/ssbot/hs_s5_fa6c11a/brain` (`combat/forum_planner.py`, `combat/multi_forecast.py`).

Words used below.
- **Antic start**: the first exported frame of a family's first state (time in state 0 in every export).
- **Decision**: the frame on which the game fixes something that was still open (aim angle, side, start point,
  landing, vertical sector). After the last decision of a move its remaining path is fixed up to the measured residual.
- **L**: the reaction latency in frames from the moment a thing becomes observable to the hero's first motion. Oracle:
  STATE f -> ACTION f+2, the oracle sees a commit one frame late, so first motion at event + 4 (aimics hero finding 2).
  The idle checks used L = 2 and 4.
- **W_r**: the reaction window used for idle bodies = L + 1 frame of slack = 5 frames (0.083 s), the same as today's
  `REACT_HOLD_S = COLLIDER_TUBE_S`.
- **HeroBox**: 0.4554 x 2.2498 u at transform + (0, -0.38). v2 uses it everywhere (D1 dilation, escape library, gates).
  Today's support dilates the exported Bounds box (0.50 x 2.079); the top differs by about 0.22 u.
- **D1**: group 1 + bodies, the danger that is already decided (section 2). **Z_g**: the inescapable zone of a pending
  group-2 attack g at its decision moment, computed with D1 as terrain (section 3).

---

## 0. What v2 changes, in one page

Today the planner's safe test (`forum_planner.tick`, S = 0) asks "does the row touch the support", and the support is
the union of where each enemy might be over 0.8 s: family unions, not-started walks, idle tubes grown at top speed and
dead-reckoned along the velocity, tails anchored at the attack start, clipped afterwards by RCLIP / BODYCLIP /
TINYCLIP / RTHROW. Committed RATIO p50 is 12-15x in base and still 2.5x (k0) / 9x (k12) with the S1-S5 bundle; every
type is above the person's 1.5x; the bundle loses all-owner coverage against base (verifier: person k12 9 rows, k36
152; bot k12 31, k36 491) and was abandoned (coordinator note 14).

v2 follows the person's design literally:
1. **Idle enemy = its body.** The real collider seen now, grown over W_r only, by the measured displacement bound of its
   current state and time in state (not the type's top speed), then held in place (no dead reckoning past W_r). The
   planner replans every frame, so later drift is the next tick's business.
2. **Group 1** = every move whose remaining path is decided: non-aimed moves from antic start to the end of recovery,
   plus aimed moves after their decision (pin line, bell arc, Minister charge angle, Choristor jump landing, Tiny dive
   line, spear rule), plus projectiles in flight. D1 = bodies + group 1 + hazards + death tails + entries. A row that
   touches D1 is unsafe.
3. **Group 2** = moves whose antic has started but whose aim / side / start point is still open. For each, at its
   decision moment, the hero must be outside Z_g computed with D1 as terrain (an escape may not cross D1). When the
   decision falls inside the row, the planner knows its own position then and resolves the move exactly for that row.
4. **Not-started moves** are not in the support at all, except for the measured families whose start from idle can
   catch a hero standing right next to the body (section 1, "idle-claim breakers"): those get a small not-started
   inescapable zone (BODY+, 0.3-1.0 u, plus two facing-away / hero-below strips).

What this removes: the window and not-started layers, the family unions, the tail anchored at the start, the
dead-reckoned idle tube, and the need for the clips. What it adds: decision tracking per family, row-resolved checks
for pending and hero-dependent moves, and an escape check whose terrain is the other enemies' decided danger (today's
`_escape_fail` tests each threat against its own family template only, `forum_planner.py` l.1355-1455: an escape that
runs into a second enemy's lunge counts as an escape).

The idle claim, checked by the three classifiers: **it holds for most families and fails near the body for a few.**
No attack collider ever made a position inescapable from idle (first damage is at least 0.40-0.48 s after the antic
start). The failures are bodies: bodies that keep tracking the hero in the antic (Reed stab, Minister stance,
Clawmaiden flight and cast), colliders that grow at the antic entry (Minister AttackAntic and ParryStance), and evades
that go backward into a hero standing behind an enemy whose turn is paused (Clapper, Bellbearer) or below it
(Bellbearer). Everything was escapable from 2 u (flyers), 0.75 u (Clawmaiden), 0.3 u (Clapper, Bellbearer facing the
hero), 0.15-0.3 u (Envoy, Choristor in front).

---

## 1. Every family x state with its group

Group codes (merged vocabulary of the three classifiers):

| code | meaning | where it lives in v2 |
|---|---|---|
| BODY | idle / positioning body; no own attack without a new start | D1 body layer |
| BODY+ | BODY, and a start from it can catch a hero next to the body (idle-claim breaker) | D1 body layer + not-started dilation |
| G1 | deterministic from the antic start: template anchored at the antic-start transform and observed facing | D1 |
| G1A | aimed, decided at a known state; template anchored and rotated / mirrored at that decision | D1 from the decision |
| G1R | path decided as a rule of the hero's future path (charge end, homing, tracking start point) | D1 holds a bound; planner resolves per row |
| G2 | antic started, aim / side / position still open | Z_g at the decision (section 3); per row when the decision is inside the row |
| HC | exists only after a hit by the hero or an ally (counters, hit-started attacks) | hit branch of the rows that hit; ally / projectile trigger |
| HAZ | projectile / hazard on a decided path | D1 |
| OTHER | entries, relocations, unobserved | per row below |

Times are game seconds. "start->dmg" = antic start to first damage (min / p50 unless stated). Residual = template
error anchored as stated, +-1 frame, all damage colliders incl. multi-hit dealt 0 / eff != 0 and the body.

### 1.1 Reed (Song Reed)

| family | state(s) | group | decision / anchor | start->dmg | motion and notes |
|---|---|---|---|---|---|
| RE_IDLE | Alert (+0-dwell Choice, Back To Idle, Alert Begin, Startle, Move Cancel) | BODY+ (1.0 u, from RE_STAB) | - | - | DistanceFlyV2 5.5-9 u from the hero at 2-4 u height, speedMax 6.5, faces the hero every frame (0.5 s turn pause). Speed p50 5.9 / p99 11.0 / p99.9 19.3; toward the hero within 3 u p99 7.3 (max 21). Alert-entry carry-over 2.81 u in 6 frames in its first 0.1 s (fix_spec F2 bands). A hit sends it to Stab Pos |
| RE_STAB | Stab Pos | BODY+ (positioning) | - | 0.633 / 0.882 / max 2.167 (family) | DistanceFly to 5 u at 0.25 u height, speedMax 7; toward the hero p50 2.35, p95 8.8 u over the state (0-1.517 s). 1395 of 2078 stabs start here. A hit -> Stab Antic |
| RE_STAB | Stab Antic | G2 (start point) + G1R | side fixed at the entry (= hero side, 1925/1926); start point = DistanceFly toward (hero -+ 5 u, +2.5 u), speedMax 5, plus vy 2 decel 0.95, until the Stab 1 entry | 0.633-0.667 | body moves p50 2.13, p95 4.52, max 5.45 u during the antic (breaks "no motion in the antic"); a hit in the antic knocks it away (p5 -4.5 u); no damage exit after Stab Antic |
| RE_STAB | Stab 1-5, Stab End, Stab Recover | G1A from the Stab 1 entry | anchor = Stab 1 position, facing | first damage at the Stab 1 entry | three lunges -20 u/s along the facing and -6 down (0.067-0.1 s each, decel 0.8 between); End 0.317-0.35, Recover 0.25-0.267; residual about 2 u at Stab 1 (floor / wall contact), 0.98 u at Stab 5 |
| RE_THROW | Throw Range (+ Throw Recoil 0 s) | BODY (positioning) | - | - | DistanceFly 8 u at 4.25 u height, <= 6.5 u/s; toward the hero p95 9.4 u over 0-2.955 s; no damage collider. Gap: no body collider exported in its first frames near the hero |
| RE_THROW | Throw Antic Anim -> Throw Antic -> Throw Aim | G2 | decision = Throw Aim entry 0.250-0.283 s after the antic (p50 0.266); aim = Reed transform -> hero transform, clamped [-70, +45] deg on the hero side; spawn (+1.53, -0.54), or (+1.11, +0.48) at 10-45 deg | release 0.40-0.50 s after the decision (pin collider p50 0.683 from the antic) | Reed moves -0.65 / -0.14 u. Z_g = 0 in all 59 hero states, lat 0 / 2, open floor (empty up to L 14) |
| Pin | Fly / Stick | HAZ | from the release | - | 31 u/s straight (0.62 u per 50 Hz step), 2.03 x 0.098 u, sticks in floor / wall (collider off); a nail swat deflects it at 62 u/s with no i-frames |
| RE_DEFEND | Defend Start / Defend / Defend End | BODY (stance) | faces the hero at the entry | none without a hit | Start 0.067-0.1, Defend <= 1.017, End 0.233-0.258; DistanceFly 3 u at 0.25 u height <= 4 u/s (toward the hero p95 2.74, max 3.27 over Defend); 1296 of 1899 end without a counter. Gap: 0 testable idle-start instances |
| RE_DEFEND | Block -> Parry Y Aim -> Parry Slash (+ Multihit, Multihit Clashed, Parry Slash End, Multihit End) | HC -> G1A (side) -> G2 (sector, decided at about first damage) | side = facing at the Block entry = hero side at the hit (1300/1300); vertical sector (level / up 22.5 / down) from the hero height at Parry Y Aim (hit + 0.483-0.517) | hit + 0.483-0.517 | Block push 10 u/s decel 0.9 (about 1.5 u; 3.67 u with later hits at 10427; a 1.9 u drop at f39847); lunge about 21 u/s, Parry Slash 0.014-0.767 s; residual p90 1.34 u at the Block entry; clash -> Multihit Clashed (no damage); continuation states reach 3.7-12 u (fix_spec F1) |
| RE_EVADE | Evade Antic -> Evade | G1 (body) | direction at the Evade entry (re-faces, moves away) | body contact 0.033 / 0.167 | Antic 0.117-0.15, Evade 0.25-0.283: 30 u/s away + 5 up, decel 0.9 (away p50 3.9, max 7.2); residual p90 3.5 (walls). From Alert 53 %. Idle: 1/1664 inescapable (air, no dash, 0.5 u, frame 9) |
| RE_ENTRY | Fly In | G1 (body, world frame) | wave activation | - | 0.783-0.817 s, dy -10.0 to -17.1, dx within +-3 |

### 1.2 Minister

| family | state(s) | group | decision / anchor | start->dmg | motion and notes |
|---|---|---|---|---|---|
| MI_IDLE | Chase / Retreat? (+0-dwell Set Attack Time, Attack Choice, Evade?, Range Check) | BODY+ (1.0 u, from MI_PARRY; 0.5 u from MI_CHARGE) | - | - | DistanceFly 6-7.5 u, >= 2 u above, speedMax 7; Retreat? 8.5-11 u for 0.5-1 s; speed p99 11.9 / 11.2; toward within 3 u p99 9.7 (max 26). A hit -> Range Check -> earlier attack |
| MI_CHARGE | Attack Antic | G1A at the antic start | aim = angle to hero + (0, 1.5) at the entry, clamped +-45 deg on the facing side; error p50 0.45, p90 7, p95 27 deg (tail unexplained) | 0.483-0.524 (p50 0.516) | recoil -14 u/s along the aim, decel 0.925 (p50 2.5 u, max 5.4); collider becomes AttackAntic (0.94 x 3.04 + 1.86 x 1.28): idle-start inescapable at 0.5 u (2/118 beside, 2/84 below), never from 1 u |
| MI_CHARGE | Attack -> Multihit / Attack End | G1A | per-angle templates (unrotated residual p90 2.44 u) | - | 33 u/s along the aim, decel 0.93; toward the hero p50 5.7 (max 8.2 without a hit, 12.4 with); Multihit on contact 831/2625 (0.4 s, v 0); End 0.25-0.267; hits and parries do not cancel it |
| MI_PARRY | Parry Stance Antic / Parry Stance / Parry Stance End | BODY+ (collider grows to ParryStance 1.61 x 2.05 + 1.17 x 1.96; invincible) | - | none without a hit | antic 0.128-0.158, stance <= 0.867, end 0.233-0.258; DistanceFly 6 u, >= 2 above, <= 6 u/s (stance moves p5 -3.9 / p95 +4.6 u toward the hero); idle-start inescapable to 1 u (0.5 u beside 8/150, 1.0 u 1/37, below 0.5 u 3/69, recorded 1/49), never at 2 u |
| MI_PARRY | Parry Block -> Parry Slash 1-4 -> Parry Slash End | HC -> G1A | direction = faces the hero at the Parry Block entry (598/600); no vertical aim | hit + 0.558-0.567 | trigger: a blocked hit in the stance (600 of 2621 stances); Block recoil 20 u/s back, -4 down, then up to +10; one lunge -45 u/s forward, -20 down, then rising; four 0.033-0.067 s segments; residual p90 4.9 u at the Parry Block anchor (unexplained), 0.62 at Slash 4 |
| MI_EVADE | Evade Antic -> Evade | G1 (body) | direction at the Evade entry (away) | body contact 0.017 / 0.1 | never from idle (after Multihit 831, Stance End 483, Attack End 360, Parry Slash End 135); antic 0.083-0.1, Evade 0.4-0.433 at 25 u/s away + 5 up (p50 5.8 u); residual p90 3.3 (walls) |
| MI_ENTRY | Fly In | G1 (body, world) | activation | - | 0.8-0.817 s descent |

### 1.3 Maestro and Tiny (Song Pilgrim Maestro, Song Automaton Tiny)

| family | state(s) | group | decision / anchor | start->dmg | motion and notes |
|---|---|---|---|---|---|
| MA_IDLE | Forum Fly / Fly / Chase (+0-dwell Summon?, Attack Choice) | BODY | - | - | Forum Fly roams +-1 u around its start at <= 8 u/s, attacks after 1.15-1.45 s; Fly / Chase DistanceFlyHorizontal 9 u at <= 5 u/s; speed p99 8.5; toward within 3 u p99 5.9. A hit -> Summon? |
| MA_SLASH | Fire Antic | G2 (side only, two mirrors; decision = first-damage frame) | side = hero side at the Slash 1 entry (7922/7922); at the Fire Antic entry only 95.4 % | 0.683-0.733 (p50 0.716) | recoil 15 u/s back, decel 0.9 = exactly 2.37 u (p5 = p95); sends FIRE to one ready Tiny (AT_FIRE starts the same frame) |
| MA_SLASH | Slash 1 -> Slash 2 -> Slash End -> Slash Recover(F) | G1 once the side is set | anchor Slash 1 / Slash 2 | - | Slash Hit 1 0.067-0.092, Hit 2 0.067-0.1; lunge -10 u/s; residual 0.16 u at Slash 2 (2.4 at Slash 1 = exported flip lag); forward reach p99 3.65; hits do not cancel (1147 hit before the first damage). Idle-start 0/1788 |
| MA_DEFEND | Defend Start / Defending / Defend End | BODY (tracking) + the Tinies' orbit | faces the hero at the entry | none (body) | Start 0.233-0.483, Defending 1.75-1.783 (DistanceFlyHorizontal 4 u, <= 5 u/s, toward p50 6.6 / max 8.2 u over the state), End 0.25; idle-start marginal 2/1784 (below 0.5-1.0 u, no dash, frame 8) |
| MA_SUMMON | Call -> Summon -> Summon Recover | BODY (no damage) | - | - | Call 0.483-0.517, Summon 0.25, Recover 0.233-0.255; body <= 1.2 u; spawns Tinies (AT_ENTRY). Idle-start 0/1696 |
| MA_ENTRY | Fly In | G1 (body, world) | activation | - | 0.8-0.817 s, dy exactly -10.0 |
| AT_IDLE | Ready / Returned | BODY | - | - | follows the Maestro's formation; speed p50 6.0, p99 7.57; toward within 3 u p99 7.5 (max 22); up to 6 at once |
| AT_FIRE | Fire Ready | G2 (side + start point) + G1R | side = hero side at the Fire entry (99.91 %; 92.6 % at the Fire Ready entry); start point moves dx p50 +2.85, +-5-7 u, dy p50 -1.25 | Fire entry 0.699-0.766 after the antic; body contact p5 0.899 / p50 1.308 | in sync with the Maestro's Fire Antic |
| AT_FIRE | Fire -> Brake -> Pull Up / Wall Bonk -> Return | G1A from the Fire entry | fixed line -53.1 deg (p1 -54.7, p99 -51.6) from the Fire-entry position | - | 48-50 u/s, Fire <= 1.0 s (p50 0.35), Brake 0.41, Pull Up 0.37, Wall Bonk 0.333-0.367, Return <= 2.07; body only, no homing. Idle-start 0/1790 |
| AT_DEFEND | Defend Ready -> Defend Buzz | G1 relative to the Maestro (G1R through its tracking) | orbit +-216 deg/s, radius 5.0 -> 2.4 (0.55 s) -> 5.08, about 19 u/s; centre = the Maestro (tracks the hero to 4 u) | body; contact p5 0.373 / p50 1.232 | residual against its own start p90 6.5 u; idle-start 5/1790 (below 0.5-1.0 u frame 5; 1 recorded position without a dash) |
| AT_ENTRY | Swoop In Pause -> Swoop In | G1 (body, world) | summon | - | pause 0-0.25, Swoop In 0.517-0.567, dy exactly -9.0, dx 0 |
| AT_LEAVE | Leave Pause -> Leave | BODY / G1 body | - | - | Leave Pause 0.316-0.766 (+-3.8 u), Leave 1.04-1.07 (+-15 u sideways, +9 up); 0/1276 |

### 1.4 Envoy (Song Pilgrim 01)

| family | state(s) | group | decision / anchor | start->dmg | motion and notes |
|---|---|---|---|---|---|
| EN_IDLE | Walker | BODY (+ contact resolution 0.15-0.3 u) | - | - | body 1.16 x 2.01; 2.40 u/s (p99 2.88) ALWAYS toward the hero; frozen-hero 0.2 s contact never (31k frames); walking gap >= 3.24 u; -> Slash Antic 68 % / Charge Antic 13 % |
| EN_IDLE | Walker + TOOK DAMAGE -> Leader? -> Charge Antic | HC (start trigger, not a counter) | direction = FaceObject(target) at the Charge Antic entry | 0.483-0.517 from Charge Antic | 23 of 28 hit windows start a charge (13 % without a hit) |
| EN_IDLE | Attack Wait, Alert Followers, Hop Up?, Leader? | BODY | - | - | Attack Wait 0-0.27 s, others 0 s; Hop Up? faces the hero then Slash Antic |
| EN_SLASH | Slash Antic > Slash1 > Slash1 2 > Slash1 Recover > Combo? > Attack End | G1 + random branch (Combo? -> JumpSlash 50 %) | facing at the Slash Antic entry (hero in front 3887/3887), no re-turn | 0.483 / 0.508 = P1 BACKSWING behind and above (x' -2.47..-0.91, y +0.58..+2.14); front P2 from 0.683 | residual p95 0.0 (max 4.06); antic motion p95 0 (2.25 u = Recoil 15 u/s x 0.15 s when hit); hits 303/3962 knock back 2.25-3.6 u, no cancel; hero already behind at first damage 14 % |
| EN_JUMPSLASH | JumpSlash Antic > Forward > JumpSlash 1-4 | G1 | facing kept from Combo? (or Charge ATTACK) | 0.400 / 0.417 | antic 0.35, Forward 15 u/s, 1.04 s; residual p95 0.51 (max 2.1); hits push p50 -1.6 u |
| EN_CHARGE | Charge Antic > Charge > (Reset / Wall Bonk / Deflect / Bump Up) > Charge End | G1 (direction, timing) + G1R (length) | direction = hero side at the entry (887/889) | 0.483 / 0.500 | 13 u/s; Charge Damager 3.2 x 1.16 at floor + 0.53..1.69; FSM end: 4 u past the hero, or past it with no floor, or vx 0 at a wall (recorded end p50 1.8 u past, p5-p95 -4.4..+4.4); length p50 14.5, p95 26.6, max 31.3; hit -> Reset -> continues (pushed p50 3.6 u); parried -> Deflect -> stops |
| EN_AMBUSH | Ambush Antic > Ambush 1 > Ambush 2 | G1 (body, wave-0 entry) | in place | body damager 1.25 / 1.282 | hero 11.4-19.4 u away in all 278; then Charge Antic 77 % |
| EN_HOPSLASH | HopSlash Antic > HopSlash 1-4 | G1 by the FSM (never observed, 0 in 490 fights) | - | - | 15 u/s forward + vy 10, JumpSlash damagers |
| EN_ENTRY / Wake / Pray | - | not observed | - | - | 0 in 490 fights |

### 1.5 Choristor

| family | state(s) | group | decision / anchor | start->dmg | motion and notes |
|---|---|---|---|---|---|
| CH_IDLE | Battle Idle | BODY (+ 0.15-0.3 u) | - | - | Body Damager 0.88 x 2.15; v 0 (p99 0.001 u/s), faces the hero every frame, dwell 0.2-0.3 s; frozen-hero 0.2 s contact 0.012 % of frames, all from gap <= 0.32 u. The body stays a damager after Slash Recover and Enter Land (the verifier's own-support hole) |
| CH_HOP | Hop Antic > Hop Back / Hop Forward / Hop Up > Ground Check > Hop Land | G1 (body) + G1R (direction) | direction at Hop Check 0.15 s: Forward only if hero dx > Hop Distance 6-10 u (recorded min 3.42) | body only | 12 u/s (Hop Up 15 + vy 14); frozen-hero contact up to 1.25 u; front escapable from 0.16 u; BEHIND without a dash inescapable to 0.5 u (19/30 at 0.2 u), only when it faces away |
| CH_SLASH | Slash Antic > Slash Antic Jump > Slash 1 > Slash 2 > Slash End > Combo? > [ComboSlash Antic1 > Antic2 > ComboSlash 1-3] > Slash Recover | G1 + random branch (combo about 2/3, decided at Combo? about 0.85 s, no re-face) + terrain stops | facing at the entry (3384/3384), no re-turn | 0.627 / 0.642 | 15 u/s lunges stopping at edges; 1.08 s (no combo) / 1.93 s; residual p95 4.7 u at 1.68 s (combo + edge / wall stop); hits 767/3531 knock back +-3.6, no cancel; hero behind at first damage 25 % |
| CH_WHIP | Whip Antic > Whip 1-6 > Whip End (Multiwhip) | G1 | faces the hero at the entry | 0.807 / 0.833 (Whip Hit dealt 0, eff 2) | 10 u/s lunge with decel; 1.23 s; residual p95 0.2 (max 2.05); Multiwhip 0.74 s only after catching the hero |
| CH_JUMP | Jump Antic > (Wait for Ground) > Jump Launch > Jump Rise > Jump Spin > Spin Slash > Spin Slash End | G1A at the antic start | Jump X = clamp(1.2 (hero x - x), +-15), vy 30; landing x' = 1.037 hero dx + 0.04 (residual p95 0.85, max 2.17) | 0.750 / 0.781 airborne Spin Hit; landing Spin Slash 1.283 / 1.308 | needs 6 u clear above; no aim-conditioned front position inescapable |
| CH_ENTRY | Battle Wake > Enter Antic 2 > Enter Leap 2 > Enter Fall > Enter Land | G1 (body, world) | faces the hero at Enter Leap 2 | body 0.383 / 0.400 | residual 0.5, 1.05 s, then Battle Idle |
| CH_IDLE | Walker, Sing, Alert, Unalert, Wait | BODY (before the battle loop) | - | - | Sing / Alert set vx 0; TOOK DAMAGE -> Alert |

### 1.6 Clawmaiden (Song Handmaiden) and the spear

| family | state(s) | group | decision / anchor | start->dmg | motion and notes |
|---|---|---|---|---|---|
| CM_IDLE | Fly (+ Set Distance, Tele?) | BODY+ (0.75 u) | - | - | body 0.87 x 3.2; DistanceFly 7-10 u, >= 3 u above (p50 3.3); speed p50 6.1, p95 8.5; toward p99 8.4 when farther than the Fly Distance; recorded min gap 0.16 u; frozen-hero contact max gap 0.57 u |
| CM_FLYTOSLASH | Fly To Slash | BODY+ (0.75 u; homing) | - | - | <= 1.0 s, homes to 4 u at hero height +1 at <= 5 u/s (moved p50 2.6, max 5.0); front inescapable to 0.67 u, back to 0.4 u, under the body without a dash to 0.75 u; -> Slash Antic 64 % |
| CM_SLASH | Slash Antic | G2 (side; decision = first-damage frame) + G1R (drift) | side = FaceObject(hero) at the Slash 1 entry (turned 9.7 %, all toward the hero) | 0.500-0.517 | DistanceFly 2.5 u/s + carry: back p50 0.75 / p95 1.25 / max 3.05, +-1.2 vertical; starts only with the hero in Slash Range (dx' 0-4.6, dy -3.1..+4.0); residual p95 4.4-6.6 anchored at the antic, 2.0 (max 3.9) re-anchored at Slash 1 |
| CM_SLASH | Slash 1 > Slash 2 > Slash 3 | G1A from Slash 1 | anchor Slash 1, decided side | first damage at Slash 1 | lunge 20 u/s decel; Slash Collider 1 4.7 x 3.0 |
| CM_SLASH | Slash 4 > Slash 5 > Slash Recover | G2 (second side decision at the Slash 4 entry, about 0.25 s after Slash 1; flip 21 %) | FaceObject(hero) again | - | +20 u/s by scale (backward against the new facing); Slash Recover 0.15-0.18 body only; total p50 0.99 s |
| CM_SPIN | Spin Antic > Spin 0-2 > Spin Wind Down > Spin End | BODY+ (moving body, no attack collider) | - | - | silk suck, no damage; holds 8 u (Spin End 12 u) at 7-9 u/s; frozen-hero contact max gap 1.3 u |
| CM_SPIN | Spear Cast Antic > Spear Fire | G2 (spear) | decision = Get Antic Angle on the Spear Fire frame, 0.45 s after the cast antic; aim spear transform -> hero transform + (0, 0.25), clamped +-45 deg on the facing (Fire L FloatClamp 135-225) | fire 0.85-0.95 s after the decision; first damage from Spin Antic min 4.82 | body rises 0.42, back 0.61 (cast-antic idle-start: back 26/30 at 0.2 u, 0 from 0.6 u). Z_g = 0 in all 59 states x 3 phases, lat 0 / 2 (empty to L 30) |
| Spear | Antic > Fire > Chase > Explode | G1R (homing) + HAZ | rule decided; path depends on the hero | - | pull-back 30 u/s x0.875 per step (3.645 u open; blocked or slid by a wall), then 37 u/s + ChaseObjectWisp force 45 toward the hero transform (to 50.9 u/s); detector from Fire + 0.1 s; ends floor 753 / wall 147 / roof 3 / hero 394; explosion r 3.5529, 0.9 u ahead, on 0.067-0.108 s; drift p50 8.9, max 29.9 deg |
| CM_TELE | Tele Out Antic > Tele Out > Select Target > Tele Pos > Tele In > Tele In End > Did Roar? / Roar | G1 (body relocation) | random arrival | - | Tele Out Antic 0.175-0.2 s drops 1.34 u (contact max gap 0.67); body damage off from Tele Out until Fly; back at 1.0-1.07 s at >= 3.64 u from the hero (p1 4.18, p50 10.9): no inescapable arrival |
| CM_ENTRY / Startle / Roar / Sing | Wake, Startle, Roar | OTHER (not measured) | - | - | Startle 0.35 s (vy +12), Roar 0.5 s |

### 1.7 Bellbearer (Pilgrim 03 Song) and the bell

| family | state(s) | group | decision / anchor | start->dmg | motion and notes |
|---|---|---|---|---|---|
| CB_IDLE | In Range / Out of Range / Insta Throw? / Startle | BODY (+0.3 u) + strips (see BODY+) | - | - | k0 envelope 1.3 x 1.5 u; DistanceFly 8 u, 4 u above (speedMax 5 + ShoveFromWall 15); speed p50 5.0, p99 21.6 (max 171 = glitch); toward when the hero is < 1 u: p50 -0.4, p99 4.8, max 23.2; attacks after 0.8-1.5 s in In Range |
| CB_THROW | Throw Evade + Roof Avoid + Throw Antic (same frame) | G1A at 0 s | Spit X = clamp(1.15 (hero x - x) + U(-1, 1), +-15), abs(vx) >= 4, vy 20 | release 0.617 / 0.666 / max 0.721 | body in the antic 0.94 back / 0.47 up (p95), max 2.7 -> release point uncertain by that; only U(-1, 1) unknown after frame 0 (about +-1 u at landing); Roof Avoid vy -15 when the roof is < 3 u; bell armed in Throw Antic 39/8737 (lead unmeasured) |
| CB_THROW | Throw / Recover / Rethrow? | G1 (body; bell out) | - | - | Recover 1.016, Rethrow? 1.18 then In Range; never rethrows; hit 13.2 % (Recoil 15 u/s x 0.15 s per hit) |
| Throwing Bell | Air / Bounce | HAZ | from the release | - | circle r 0.425; 50 Hz semi-implicit Euler, g 60, vy 20; floor bounce restores vy 20; wall sends it back at vx 10; a nail hit redirects it at 30 u/s and it becomes harmless |
| CB_EVADE | Evade Antic | G1 (body) | faces the hero (FaceObjectV2, 0.5 s pause) | 4-5 frames | antic dx p50 0.28, max 2.47 |
| CB_EVADE | Evade / Evade End | G1 (body) | backward by the facing | body | 32 u/s backward, -8 down, x0.9 per frame: 4.3 u away, drop 1.25 (p99 1.39, max 3.46); 0.40-0.425 s. Facing away (11/3418): goes INTO the hero, inescapable to 2-3 u. Hero below (abs dx <= 1 u): inescapable for a gap <= 1.5 u (2.0 escapable; 3 u with the 3.46 u outlier) |
| CB_ENTRY | Fly In Instant / Battle Fly In / Check Pos / Shift / Fly In / Activate | G1 (body, world) | - | - | 0.78-0.82 s |
| CB_SING / FSM Force* | Sing, Sing End / Force Up / Down / Left / Right | OTHER | - | - | Sing needs Needolin (never seen); Force* are flyer shoves of the body |

### 1.8 Clapper (Song Heavy Sentry) and its hazards

| family | state(s) | group | decision / anchor | start->dmg | motion and notes |
|---|---|---|---|---|---|
| CC_IDLE | Idle | BODY (+0.3 u) + facing-away strip | - | - | k0 envelope [-1.341, -4.434, 2.045, -1.255], 2 damage; 0.65 s alone / 1.15 s with a buddy; vx 0; faces the hero (0.5 s pause); toward when < 1 u p99 0.05 |
| CC_IDLE | Walk | BODY | - | - | DistanceWalk 7 u +-1.5 at 8 u/s (measured p50 9.6, p99 14.4); approaches only beyond 8.5 u, backs off inside 5.5 u; toward when < 1 u p99 1.5 |
| CC_IDLE | Close Range / Far Range / After Scuttle / Avoid Type / Z Set / Escape Jump | BODY (0 s decisions) | - | - | Close: SLAM / EVADE / CAST (Walk B forces SLAM); Far: JUMP 0.5 / CAST 0.25 / JUMP_CAST 0.25; cancel to Idle while the buddy attacks |
| CC_IDLE | Dmg Attack | HC (start trigger) | - | - | a hit in Idle skips the remaining 0.65-1.15 s wait |
| CC_SLAM | Slam Antic | G1 | turns to the hero at the entry (2088/2091) | Slam 0 at 0.783-0.817; first damage 0.85 / 0.899 | body 0 (p99 0.24, max 0.63; hits <= 1.44) |
| CC_SLAM | Slam 0 / Slam 1 / Slam Effects? / Slam 2 / Slam Recover | G1 (re-anchored at Slam 0) | Slam 0 entry | - | lunge 30 u/s: 2.1 / 3.6 / 4.8 u (p1 / p50 / max; shorter at a wall); collider 1 -> 2 switch jitter +-3 frames; residual p95 back 3.8, bottom 1.9, front 2.7, top 0.6; 2 damage; no clash; ends about 1.29 s; hit in 40 % |
| CC_EVADE | Evade Scuttle | G1 (body, NO antic) + BODY+ strip when facing away | backward by the facing | body from frame 0 | 15 u/s for 0.35-0.367 s (5.4 u); box +0.21 front, +0.72 top at the entry; toward a faced hero 0/6719. Facing away (4/7914): inescapable to 2 u without a dash (full lib L2), 1 u with a dash (coarse L4), >= 3 u with a wall behind. A wall within 6 u behind -> Escape Jump -> JUMP / JUMP_CAST |
| CC_CAST | Spell Antic / Cast 1 | G1 (no damage) | - | - | Cast 1 0.72-0.82, Cast 2 0.80-0.92; body <= 0.54 (<= 1.44 with hits) |
| CC_CAST | Cast 2 -> bombs (Bomb Cast FSM) | HAZ (row fixed at Cast 2) | x_c = the Clapper's x at Cast 2 | first damage 0.824 / 1.182 (m = 0) | circles r 2.166 at x_c + 4.2 m (abs(m) <= 9, +-0.33), floor + 0.65; bomb m appears at Cast 2 + 10 abs(m) frames, arms 21 frames later, lit p50 6 (5-17); walls / pool cut the row; neighbours overlap (4.2 < 4.33): the floor is fully covered, the escape is a jump |
| CC_JUMP | Jump Antic | G2 | decision = Jump Aim 0.483-0.517 s (frames 28-30); target = hero x - 5 u (facing frame after the Jump Aim turn); vx = clamp(target - x, +-12), vy 38; landing = x + 0.916 vx | decision -> first damage 0.915 | body 0 (<= 0.63; <= 1.2 with hits); landing error p50 0.03, p95 0.39 (errors > 2 u only at walls); Z_g empty beside |
| CC_JUMP | Jump Aim / Jump / Air / Charged? / Slam Effects? / Slam 2 / Slam Recover | G1A | landing | 1.157 / 1.415 (landing Slam Collider 2) | ends 1.75; body (2 damage) on the arc, apex +8.2; hit in the air 773/4005 (landing error p95 0.65) |
| CC_JUMP_CAST | Cast Slam Antic / Cast Slam Antic 2 / Cast Jump | G2 | decision = Jump Aim 0.883-0.933 s, same rule | decision -> first damage 0.915 (Slam 2 1.182 / 1.848) | body <= 0.48 (<= 1.44 with hits); ends 2.18 |
| Rune slam | spawned at Charged? (landing) | HAZ (aimed through the landing) | centre 6.48 u in front of the landing at floor + 0.33 | arms 65 frames (1.06-1.11 s) after the landing, lit p50 8 (<= 20); about 2.9 s after the antic | circle r 7.187, 2 damage; hits only inside (max +0.23 u = HeroBox top). Truth gap: 109 of 1069 lit windows with > 0.3 u penetration logged no damage |
| CC_ENTRY / CC_SING | Drop Antic ... Roar End / Sing | OTHER | - | - | entry 4.25 s body only (n 1); Sing needs Needolin |
| (hits on it) | every attack state | push only | - | - | no TOOK DAMAGE transition in attacks: no cancel, stagger or counter; push 0.24-1.44 u, mostly Garmond |

### 1.9 Contradictions between the classifiers, the person's rules and earlier results

C1. **"Enemies do not move in their antic"** is false for six states: Reed Stab Antic (tracks the hero, p95 4.52 / max
5.45 u), Minister Parry Stance (+-4-5 u), Tiny Fire Ready (+-5-7 u), Clawmaiden Slash Antic (back max 3.05, +-1.2
vertical), Spear Cast Antic (0.42 up, 0.61 back), Tele Out Antic (1.34 u drop). Deterministic recoils (not tracking):
Minister Attack Antic 2.5 u (max 5.4), Maestro Fire Antic exactly 2.37 u, Bellbearer Throw Antic 0.94 / 0.47 u p95
(max 2.7), Reed Block push, Minister Parry Block 20 u/s back. Hit recoils in antics are frequent (Envoy / Choristor
2.25-3.6 u; Clawmaiden p50 2.0 u, up to 8-10). In v2 the tracking antics are G2 / G1R (the planner resolves them per
row), the recoils are part of the G1 templates, the hit recoils go into the hit branch.

C2. **Reed Block push.** Flyers: about 1.5 u (10 u/s, decel 0.9). fix_spec 10427: 3.67 u. S1: a 1.9 u drop after a hit
at f39847. The push grows with hits during Block; the template needs a per-extra-hit push (a hit branch), not one value.

C3. **"Every move re-faces the hero at its antic entry"** (flyers; they dropped all hero-behind placements as artifacts)
against the heavy classifier: the evade direction is backward from the FACING, and when the enemy turned less than
0.5 s ago FaceObjectV2's pause leaves it facing away, so the evade goes into the hero (Clapper 4/7914, Bellbearer
11/3418, inescapable to 1-3 u). The ground classifier notes the same risk for the Choristor / Envoy back side. Both are
right for what they measured; v2 takes the facing from the observed flip and the turn history, not from "faces the
hero". The flyers' dropped hero-behind cases must be re-checked under this rule for RE_EVADE / MI_EVADE (gap).

C4. **"Idle enemies do not walk into you"** holds on average (DistanceFly standoffs: Reed 5.5-9 u, Minister 6-7.5,
Clawmaiden 7-10, Bellbearer 8, Clapper Walk backs off inside 5.5, Choristor still) but not as a short-time bound:
Envoy Walker walks toward the hero at 2.4 u/s ALWAYS (it attacks before contact); toward-the-hero speeds within 3 u:
Reed p99 7.3 (max 21), Minister p99 9.7 (max 26), Clawmaiden p99 8.4, Tiny 7.5, Maestro 5.9, Bellbearer (< 1 u) p99 4.8
(max 23.2, not split into ShoveFromWall vs recoil), Clapper 0.05-1.5. The person's frozen-hero 0.2 s version fails for
the Clawmaiden (0.57-1.3 u) and, by the speeds, for the Reed and the Minister. The escapability version (L = 2-4)
holds with the BODY+ margins below. So v2 grows idle bodies over W_r only, by state.

C5. **Idle-claim margins differ by protocol**, so they are not comparable yet: flyers body + 1.0 u (coarse library,
clearance 0 = pure touch, hero at rest, no walls); ground body only / Clawmaiden + 0.75 u (coarse, T 150, 0.1 u raster
= 0.15 u contact resolution, 30 instances); heavy + 0.3 u (coarse + full L2 for ground, clearance 0.05, wall 0.3 u,
11 states). Bounds vs HeroBox also differ. One protocol must re-run the breakers (round V0).

C6. **Reed Stab Antic speed.** fix_spec F2: "its body moves about 21 u/s in Stab Antic while the exported velocity is
about 4 u/s". Flyers: moves p50 2.13 / p95 4.52 / max 5.45 u over the 0.633-0.667 s antic (about 8.6 u/s at most on
average). 21 u/s is probably the Stab 1 lunge or a transform-vs-velocity artifact; not resolved.

C7. **MI_CHARGE "decided at the antic start"**: rule error p50 0.45 deg but p90 7, p95 27 deg. Either a later re-aim
in 5-10 % or a measurement artifact (rotated sprite). Until resolved, the G1A template carries an angle margin from
the held-out residual and the tail is listed as a precision exception.

C8. **"Pending" moves whose decision is the first-damage frame** (Maestro slash side at Slash 1, Clawmaiden side at
Slash 1 and Slash 4, Reed counter sector at Parry Y Aim): G2 by the person's definition, but decision -> damage is
0 s, so the zone at the decision is just the strike region of every option. v2 treats them as G1 with all options
(shared D1) and resolves the option per row (the row knows which side the hero is on at that frame).

C9. **CH_HOP** classified IDLE by the ground classifier, but it is a 12-15 u/s body move after a 0.15 s antic with
frozen-hero contact to 1.25 u and a behind-side breaker: merged as G1 body with a rule-decided direction.

C10. **strikes.json minima** CB_THROW 0.0 s and CC_CAST 0.117 s are earlier hazards still alive (per instance: 0.617
and 0.824 s); RE_STAB min 0.617 (fix_spec sec. 5) vs 0.633 (flyers, from Stab Antic). v2 builds its own per-instance
timing table from R0 dev.

C11. **Pin timing.** The person assumed decision 0.5 s, release +0.1 s; measured decision 0.266 s, release +0.40-0.50 s
(plus about 0.29 s of flight). With the measured timing the zone is empty everywhere; with the person's it is not.

C12. **"The pin zone is empty" vs the re-score's pin misses.** Not a contradiction of the zone: S1 found 5 pin rows
(20261004_002749 a4 f21318-21324, a15 f71084-71087) that the planner's aimed check `_pin_contacts` called safe and
that base held only through the Envoy's charge box. The v2 per-row pin rule must catch them (regression set).

C13. **Envoy facing / front.** Its first damage (P1, 0.483 s) is a backswing BEHIND and above the body; front P2 starts
at 0.683 s. "Danger in front" intuitions and any facing inferred from the first collider are wrong.

C14. **EN_CHARGE "deterministic"**: only its direction and timing; its length depends on where the hero is (4 u past
it) and on walls (p95 26.6 u). G1R.

### 1.10 Gaps (needed before the corresponding part is trusted)

1. Reed RE_DEFEND and RE_THROW: 0 testable idle-start instances because no body collider was exported in the first 6
   frames of Defend Start / Throw Range near the hero. Is the body really off (then BODY is smaller) or not exported?
2. MI_PARRY residual p90 4.9 u at the Parry Block anchor (vertical carry-over or the rotated sprite suspected).
3. P(counter | hit in Defend) for the Reed, and which hits do not trigger (kill, stagger, hits in Block, Garmond's,
   projectiles) - fix_spec sec. 7 asked, not measured.
4. Hit sources are pooled (hero / Garmond / Shakra / projectiles); the RCLIP=2 trigger models only melee.
5. Every idle check is open floor (no blockers / other enemies), coarse library (full only for some heavy cases), R0
   only (107 fights; ground used 490 incl. R1c), hero at rest or a few vy bins.
6. Facing-away variants for the flyers' evades (C3) and the turn-pause rule per state (pauseBetweenTurns from the FSM
   decodes in `C:/ssbot/sandbox/reactive_scripts/out/`).
7. AT_DEFEND is deterministic only relative to the Maestro, whose Defending tracks the hero (nested G1R).
8. CM_ENTRY / Startle / Roar, EN_HOPSLASH, EN Wake / Pray, CB / CC Sing: unmeasured or never seen (G1 by the FSM as a
   fallback; flag `unknown` if seen).
9. Runtime "locked" hero states (bind, recoil, hurt, umbrella / glide, pogo, air dash, wall cling) are not detected;
   aim_ics maps them to a `locked` key that is inescapable everywhere.
10. aim_ics boundary: the hero is sampled per physics step at ceil((n - phase) x 1.2); the verifier says the 0.1 u
    clearance does not cover the in-frame position uncertainty. Zones near their edge may be slightly too small.
11. Rune slam: 109 / 1069 lit windows with > 0.3 u penetration and no damage event (truth); bell early arming lead in
    Throw Antic (39 / 8737); CH_SLASH back-side outlier (1/30 up to 1.75 u).

---

## 2. D1: group 1 + bodies

D1 is one shared, time-indexed lethal set over [0, H] (H = SUP_HORIZON_S 0.8 s, extended past H only by the light cone,
sec. 4). Every live, in-play enemy always contributes at least its body, so no enemy ever has an empty own support.

### 2.1 Body layer (every live enemy, every tick)

- Box = the enemy's real damage collider(s) seen at the latest sample (`tr.seen_box`, or the type hull at `tr.pos` if
  the box is missing). Mid-move the body is the template's body (2.2) and this layer only adds the end-of-move hold.
- Growth over W_r only: a per (type, state, time-in-state band, hit / no hit) displacement table, max over W_r frames
  of the body box's displacement in each of the four directions (facing frame), fitted on R0 dev, 2-fold held-out
  margin. Bands: < 0.1 s / 0.1-0.5 s / >= 0.5 s (fix_spec F2; the Alert-entry carry-over sits in the first band). The
  rows use dead reckoning only inside W_r; after W_r the grown box is held where it is.
- Expected sizes (from the classifiers, p99 toward the hero x 0.083 s): Choristor Battle Idle 0; Clapper Idle 0.0,
  Walk 0.13; Envoy Walker 0.24; Bellbearer 0.4; Maestro 0.5; Reed 0.6; Tiny 0.63; Clawmaiden 0.7; Minister 0.8 u.
  (The table, not these numbers, is what ships.)
- Hit-conditioned growth only for plan rows whose swing reaches the enemy (the planner's hit branch) and while an ally
  or a hero projectile can reach it (2.4).
- End-of-move hold: when a G1 template ends inside H, its last body box is held from the template's end to H, grown
  by the next state's band (Battle Idle after Slash Recover, Attack Wait after Charge End, Chase after Evade / Fly In,
  Fly after Defending). This closes the three holes the verifier and S2 / S3 found (sec. 2.6).

### 2.2 G1 / G1A templates (moves under way)

Per family, built from R0 dev only (107 fights):
- **Node chain per family**: one node per state, each with its own anchor rule: the antic start (position + observed
  facing) for G1, the decision state's entry for G1A (fix_spec F1 option 1, "dec" nodes). Examples: RE_STAB re-anchors
  at Stab 1; RE_DEFEND counter at the Block entry (side) and the Parry Slash entry (lunge); MI_PARRY at Parry Block;
  MA_SLASH at Slash 1 / Slash 2; CM_SLASH at Slash 1 and Slash 4; CC_SLAM at Slam 0; AT_FIRE at Fire; CH_JUMP /
  CB_THROW / MI_CHARGE at the antic start with their aim parameter.
- **Shapes**: per frame offset from the node anchor, the AABBs of every damage collider (multi-hit dealt 0 / eff != 0
  included) and of the body, in the facing frame; aimed nodes keyed by the aim parameter (angle bin for MI_CHARGE; the
  measured rule is applied, not a bin union, where the residual allows: CH_JUMP landing = 1.037 dx, CB bell arc,
  AT_FIRE -53.1 deg line).
- **Kinematic split for lunges with large residual** (CH_SLASH 4.7, EN_CHARGE, MI_CHARGE 2.44 unrotated, RE_STAB 2.0 at
  Stab 1, CC_SLAM, every evade 3.3-3.5 u): template = body path from the FSM velocities (20 u/s decel 0.8, 30 u/s,
  15 u/s, ...) + collider shapes relative to the body. The path is clamped by the arena terrain (walls, edges, floor),
  which is where most of the residual comes from (CH_SLASH residual correlates 0.52 with wall distance).
- **Branches**: random branches stay a union only until their decision: CH_SLASH combo (2/3 at Combo? about 0.85 s),
  EN_SLASH -> JumpSlash (50 % at Combo?). Each branch carries its probability for FORCED_RISK.
- **Margins**: per node, per time bin, per side: the 2-fold held-out residual quantile (no global r, no family 2.62 u
  margin). A node whose margin would exceed 1 u is listed (sec. 5.2) and gets re-anchored or split, not padded.
- **Facing**: the observed flip at antic start + 1 frame (the flip export lags a frame: MA_SLASH 2.4 u at Slash 1); if
  the FSM rule (face the hero) and the flip disagree and the turn pause cannot have blocked the turn, the rule wins; if
  it is ambiguous, both mirrors for that frame only.
- **Duration**: through the end of the family's recovery state (Slash Recover, Attack End, Charge End, Spin Slash End,
  Stab Recover, Evade End, ...), then the end-of-move hold (2.1). No separate "tail" anchored at the start.

### 2.3 G1R: moves decided as a rule of the hero's path

| move | rule | shared D1 bound | per-row resolution |
|---|---|---|---|
| RE_STAB Stab Antic start point | DistanceFly toward hero -+ (5, -2.5) at <= 5 u/s + vy 2 decel 0.95 | the start point's reachable set from now to Stab 1 (<= 5 u/s x remaining time, capped by the recorded 5.45 u), then the lunge from every point of it | simulate DistanceFly against the row's hero path; lunge from the resulting Stab 1 point |
| EN_CHARGE length | ends 4 u past the hero, no floor, or wall | the line to the wall / edge in the charge direction | end = 4 u past the row's hero x at the passing time (+ recorded slack +-1.8 u) or the wall |
| Spear flight | ChaseObjectWisp force 45 toward the hero transform, speed clamp [running max, 50] | cone of +-30 deg drift (recorded max 29.9) along the decided aim, to the terrain, + explosion r 3.553 | simulate the homing against the row's hero path (50 Hz, end-of-Fire error p50 0.000) |
| Tiny Fire Ready start / side | side = hero side at Fire; start drifts +-5-7 u | both sides, start box = recorded drift envelope | side and start from the row at the Fire entry window |
| CM_SLASH antic drift / side | DistanceFly 2.5 u/s + carry; side at Slash 1 | both sides, drift envelope (back 3.05, +-1.2) | side from the row at the Slash 1 window; drift from the row's distance |
| CH_HOP direction | Forward only if hero dx > 6-10 u at Hop Check | both directions | from the row's dx at Hop Check (0.15 s) |
| AT_DEFEND orbit centre | the Maestro's DistanceFlyHorizontal (4 u, <= 5 u/s) | orbit around the Maestro's reachable set | Maestro path from the row's hero path |

The shared D1 bound is what the overlay draws, what the group-2 escapes treat as terrain, and what FORCED_RISK ranks
with. The planner's S test uses the per-row resolution, which is exact by the measured rule (no union).

### 2.4 Hit-conditioned branches (HC)

Only for plan rows whose own swing reaches the enemy at t_h (`sc["first_f"]`, the existing `_hit_branch`), and for an
ally / projectile trigger:
- Counters. RE_DEFEND: Block from t_h, side = the row's hero side at t_h, push per hit, Parry Y Aim sector = the row's
  hero height at t_h + 0.483-0.517 when that time is inside the row (else the three-sector union), Parry Slash from the
  Parry Y Aim position. MI_PARRY: Parry Block from t_h (only for blocked hits in the stance), direction = the row's
  side at t_h, one lunge template.
- Knockback of a move under way: the move's template widened by the per-hit recoil table (15 u/s x 0.15 s, Envoy /
  Choristor 2.25-3.6, Clawmaiden p50 2.0 up to 8-10, Minister Attack +4.2 u forward, Clapper <= 1.44).
- Hit-started attacks (Reed Alert -> Stab Pos -> Stab Antic, Minister -> Range Check, Maestro -> Summon?, Envoy Walker
  -> Charge Antic 23/28, Clapper Dmg Attack): they start reactively like any other start; the only change is that the
  enemy's BODY+ dilation is active from t_h even in states whose dwell would forbid a start.
- Ally / projectile trigger: an enemy that Garmond / Shakra (oracle `WorldState.allies`) or a hero projectile in flight
  can reach within the horizon gets its every-frame (hit-included) branch in the SHARED D1 from that frame. Fit the
  allies' reach on dev (today `_hero_hit_k` uses the hero's 4 u / 28-30 u/s for allies, unfitted).

### 2.5 Hazards, death tails, entries

- Pin: straight 31 u/s line from the spawn, swept per 50 Hz step, stick at floor / wall. Bell: ballistic (g 60, vy 20,
  bounce rules), from Throw Antic for the 0.5 % armed early, release point = body at release (dilated by the antic
  motion table), vx +-1 u/s. Bombs: the fixed row from Cast 2 with the arming schedule. Rune slam: the circle from the
  landing with its arming time. Spear: G1R (2.3). Hazards are their own subjects after release: a dead or unknown
  thrower no longer matters (today 1,174 unattributed rows at k0 on the person's sessions).
- Death tails: unchanged (DEATH_TAIL_S).
- Entries: per-family world templates from the wave activation (Fly In dy -10.0..-17.1, Swoop In -9.0, Enter Land,
  Ambush); parked members contribute nothing until their wave activates (PARK).
- Tinies: each Tiny is placed on its own (the pooled group rows and TINYCLIP go away; 6 Tinies x a few nodes is cheap).

### 2.6 How D1 replaces today's layers

| today (`multi_forecast._Builder.subject`, hs_s5_fa6c11a l.1227-1440) | v2 |
|---|---|
| committed: family union from the start (`fid`), per-state nodes at the start anchor, AIM templates | G1 / G1A node chain re-anchored at decisions, per-bin per-side margins |
| window: coarse family-union / walk-window placements (wm*) | gone; variable parts are explicit branches or G1R bounds |
| not_started: walk roots, start_attack bboxes, family-walk groups, PRESTRIKE | gone; replaced by the reactive start (seen within L) + BODY+ for the breakers + group 2 |
| tail anchored at the instance start (C10) | the template through recovery + end-of-move hold |
| idle tube (+g: type growth over 5 frames, then dead-reckoned along the velocity to H) | body layer: per-state W_r growth, held in place |
| collider tube (type top speed over COLLIDER_TUBE_S) | merged into the body layer |
| RCLIP / BODYCLIP / TINYCLIP / RTHROW / REANCHOR / NSBOX / WALKFLOOR | not needed (ignored under V2; GATES kept as an input to BODY+ activity) |
| hazard tubes / paths with thrower attribution | hazards as first-class subjects with deterministic paths |
| `_escape_fail` threats ("+n": every startable family template, both facings, dead-reckoned, own template only) | BODY+ for the breakers; group-2 zones with D1 as terrain; lock-in checks (sec. 4) |

The holes found by the push verifier and S2 / S3, and why v2 does not have them:
1. Choristor own support empty after Slash Recover / Enter Land from k about 9 (base held it only through other
   enemies' boxes; the clips exposed it as complete misses at 085824_a2 f32678, 231544_a1 f22099, bot i3_ep2
   f16502040, i3_ep0 f16496130): the body layer is placed for every live enemy at every tick, and the template's end
   body is held.
2. Envoy Charge End body covered only by the family union (REANCHOR fam lost 320 rows): Charge End and Attack Wait
   are template nodes; then the hold.
3. WALKFLOOR losses (body after Evade / Fly In / Defending had no owner under "+n"): the same hold.
4. Coverage that base got by accident from other owners: the v2 gate compares own AND all-owner coverage against base,
   not nested, at every k (sec. 5.1).
5. R2 not held out (R_FLOOR 0.5 u and the next-two-bins rule from R2 misses): v2 tables are fitted on R0 dev only;
   every table's source is written into a manifest.
6. Pin misses of `_pin_contacts`: replaced by the measured per-row pin rule (sec. 3); the 5 rows are a regression set.
7. Bells in flight with no path: hazards are subjects from their first frame; early arming from Throw Antic.
8. Hit trigger only melee: ally / projectile trigger (2.4).
9. BODYCLIP silently on when its table appears: v2 refuses to start if a product listed in its manifest is missing.

---

## 3. Group 2 at runtime

### 3.1 The pending attacks and their decisions

| attack | pending from | decision moment (from its antic start) | rule at the decision | decision -> damage | measured Z_g (open floor) |
|---|---|---|---|---|---|
| RE_THROW pin | Throw Antic Anim | Throw Aim entry, 0.250-0.283 s | Reed transform -> hero transform, clamp [-70, +45] on the hero side; spawn offsets | release 0.40-0.50 s, then 31 u/s | 0 in 59 states, lat 0 / 2 (empty to L 14) |
| CM spear | Spear Cast Antic | Get Antic Angle = Spear Fire entry, 0.45 s | spear -> hero transform + (0, 0.25), clamp +-45 on the facing | fire 0.85-0.95 s, then homing | 0 in 59 states x 3 phases (empty to L 30) |
| CC_JUMP | Jump Antic | Jump Aim, 0.483-0.517 s | target = hero x - 5 u; vx = clamp(target - x, +-12); landing x + 0.916 vx | 0.915 s (landing slam) | empty beside (L2 / L4, walls 0.3 u) |
| CC_JUMP_CAST | Cast Slam Antic | Jump Aim, 0.883-0.933 s | same; + rune slam r 7.187 at landing + 6.48 u | 0.915 s slam; rune armed about 2.0 s after the decision | slam empty beside; rune slam not scanned with blockers (it is the one that needs terrain) |
| RE_STAB | Stab Antic | continuous until the Stab 1 entry, 0.633-0.667 s | start point by DistanceFly (2.3) | 0 at Stab 1 (lunge reaches a still hero in about 0.25 s) | not scanned as a tracking move; idle-start inescapable to 1 u |
| MA_SLASH side | Fire Antic | Slash 1 entry, 0.683-0.733 s | hero side then | 0 | n/a (both mirrors are the zone) |
| AT_FIRE side + start | Fire Ready | Fire entry, 0.699-0.766 s | hero side then; start = Fire-entry position | dive at 48-50 u/s, body contact p5 0.2 s after Fire | not scanned |
| CM_SLASH side | Slash Antic | Slash 1 entry 0.500-0.517 s; again Slash 4 (+0.25 s) | FaceObject(hero) | 0 | n/a (both mirrors) |
| RE_DEFEND sector (HC) | Block (after a hit) | Parry Y Aim, hit + 0.483-0.517 s | hero height then -> level / up / down | about 0 | n/a (three sectors) |

Decided at the antic start, so NOT group 2: MI_CHARGE (angle), CB_THROW (vx), CH_JUMP (landing), every G1.
Simultaneous pendings exist: the Maestro's Fire Antic and a Tiny's Fire Ready start on the same frame; two Reeds can
throw together. The zone of a joint pending is not the union of the single zones, so the exact check below handles
all pendings of a tick together.

### 3.2 The safe condition per row

For a plan row r with end time T_r and its hero states s_r(t) (nominal lane + bounds_lo envelope), and each pending
attack g with decision window [t_lo, t_hi] (from the observed antic start, measured min / max, minus the age):

- **(a) decision inside the row (t_hi <= T_r):** for each frame t_d in the window, apply g's rule to the row's hero
  (transform from the nominal box; every envelope variant for the aim), build g's decided trajectory, and test the row
  after t_d against it (swept, HeroBox). This is exact for that row. It is the generalized `pin_contacts_kernel`.
- **(b) decision after the row (t_lo > T_r):** from the row's end state, an escape must exist: some escape trajectory
  e from s_r(T_r) such that e avoids D1 over [T_r, T_r + T_esc], and, with g's rule applied to e's own position at
  each t_d in the window, e also avoids g's resulting trajectory. (The aim_ics kernel is exactly this with D1 = empty
  and the escape starting at the decision; here the escape starts at T_r <= t_d, which only adds options.)
- **(c) the window straddles T_r:** both (a) for the t_d <= T_r part and (b) for the rest.
- With several pendings, (b) uses one escape against all of them (each resolved on e).
- The row's own lock-ins (attack pressed, bind, dash / sprint, no-control modes) are check points like T_r: from the
  locked state played out, the same escape test (sec. 4 item v).

"Outside Z_g with D1 as terrain" is the existence part of (b); (a) is the person's "after the decision, the decided
line"; (a) + (b) together are the person's two-group rule applied to a row.

### 3.3 The algorithm and its cost

Per tick, only when at least one pending attack exists (or a BODY+ / lock-in check needs D1 as terrain):

1. **D1 raster** (once per tick): a local window around the hero (32 x 20 u at 0.25 u = 128 x 80 cells) x 36 time
   bins of 2 frames (1.2 s past the origin, covering T_r + the escape), bit-packed, from the D1 placements (shared
   bound for G1R). About 50 placements at worst (8 enemies + 10 hazards): **0.3-0.6 ms** in numba (estimate; table D of
   the plan measured 0.36 / 1.37 ms for a 1,050-cell x 14-bin field from a full Bell Beast forecast).
2. **(a) per-row resolution** for the rows still safe after the D1 test, in the planner's priority order: 1-3 decision
   frames x 1 trajectory x the row's frames. Same cost class as `_pin_contacts`: **< 0.3 ms** for 192 rows.
3. **(b) end-state / lock-in escape**, three tiers:
   - **Tier 0, table**: the open-floor Z_g (aim_ics npz; empty for the pin, the spear and the Clapper jump at L <= 14)
     plus blocker variants (fix_spec sec. 10 addendum 3: lethal boundary on the far side, the attacker's side and
     above, at 0.5 / 1 / 2 / 3 u). Read the nearest D1 cell per side within the state's reach set over the escape
     window from the raster (time-collapsed: conservative), pick the dominating variant, look up. If "escapable" and
     only one pending: pass. Cost: microseconds per row.
   - **Tier 1, reduced library**: per hero state key (the 59 aim_ics keys), E = 32 escape trajectories chosen offline
     by greedy set cover: over the full-library scans of every group-2 family x blocker variant x phase, plus D1
     samples taken from recorded frames, repeatedly take the trajectory that is the first escape for the most
     still-uncovered (cell, variant) pairs, until 99.5 % of the cells the full library clears are cleared. Plus the 7
     escape commands of `_esc_cmds`. Test: displacements from the bin's canonical start (aim_ics libraries are
     relative displacements, so no rollout), D1 raster lookups O(1), g's trajectory resolved on e at each t_d (pin /
     slam / rune: closed form; spear: 50 Hz homing). 39 x 60 frames x (1 lookup + 1-2 swept tests) = about 2.5k tests
     = **10-20 us per check point**. Deduplicate check points by (state key, 0.25 u cell): 441 rows give about 50-150
     distinct points -> **0.5-3 ms**.
   - **Tier 2, exact rollout** for at most 16 check points per tick that tier 1 rejects and whose state is off its
     bin's canonical values by more than the bin study's spread (the verifier found h 0.45 in the h 0.25 bin gives
     6.48 vs 3.67 u2): `kin.rollout` of the 39 escapes from the real state: **about 1-2 ms** (512 x 48 nominal = 2.35
     ms in table B; 16 x 39 = 624 rows x 60 frames).
   - Safety direction: a reduced library can only clear FEWER cells than the full one, so tiers 1-2 can only reject
     more rows (availability), never pass an inescapable one; tier 0 passes only on a table built with the full
     library and dominating blockers. The share of rows rejected by tier 1 but clear in an offline full-library audit
     is reported (sec. 5).
4. The planner's deadline already cuts the envelope queue; rows not checked are not safe.

Estimated total with a pending attack: **p50 about 1 ms, p99 about 4-5 ms**, inside the plan's Forum target (tick p99
median <= 15 ms) only if D1 also makes the support cheaper (fewer placements than today's walks and unions, which is
expected). No pending attack: only the raster for lock-ins when BODY+ or a lock-in needs it.

Offline products for tiers 0-1: blocker variants per family (59 states x 3 sides x 4 distances x 3 phases x lat 2 / 4)
with the fc31849 kernel: the scans are 0-10 s each with the coarse library (exact when it finds an escape), so about
1-2 h per family at Idle priority, 2 heavy processes at most.

### 3.4 The families that break the idle claim: BODY+

A not-started inescapable zone around the idle body, only for these, only while the family can start within W_r (the
walk's dwell floor and fsm_gates; always from t_h for a row that hits the enemy):

| type, family | zone (from the classifiers; to be re-run with one protocol in V0) | why |
|---|---|---|
| Reed, RE_STAB from Alert / Stab Pos | body + 1.0 u beside and below (0 at 2 u) | Stab Antic body tracks the hero; hits at frames 2-5 |
| Reed, RE_EVADE (air, no dash) | + 0.5 u beside (1/139, frame 9) | evade body |
| Minister, MI_PARRY | body + 1.0 u (8/150 at 0.5 u, 1/37 at 1 u, below 3/69) | ParryStance collider growth + tracking |
| Minister, MI_CHARGE | body + 0.5 u (2/118 beside, 2/84 below; 0 from 1 u) | AttackAntic collider |
| Clawmaiden, Fly / Fly To Slash / Spin / Spear Cast Antic | body + 0.75 u all round (max break 0.75; under without a dash 0.75) | the body keeps moving in the latency (Fly carry up to 8.5 u/s, homing 5 u/s) |
| Clapper, CC_EVADE while facing away from the hero (turned < 0.5 s ago) | strip behind the body (backward-from-facing) 2 u without a dash, 1 u with, 3 u with a wall behind the hero | no antic, 15 u/s backward |
| Bellbearer, CB_EVADE while facing away | strip 3 u backward | 4-5 frame antic, 32 u/s backward |
| Bellbearer, hero below (abs dx <= 1 u) | strip 1.5-2.0 u below the body (3 u with the outlier) | evade drops 1.25-1.39 u (max 3.46) while sweeping |
| Choristor, CH_HOP while facing away | strip 0.5 u behind (no dash) | Hop Back 12 u/s |
| Clapper / Bellbearer facing the hero | body + 0.3 u | box growth at the antic entry (+0.21 front, +0.72 top for Evade Scuttle) |
| Envoy, Choristor (front) | body + contact resolution 0.15-0.3 u | none found |
| Maestro MA_DEFEND, Tiny AT_DEFEND (below, no dash) | + 0.5-1.0 u below | marginal (1-2 / 150-1790) |
| Maestro / Tiny other families | body only | 0 of 1276-1790 |

The shared D1 uses the no-dash (worst) value; the hero's dash state is not split in the first version. The facing-away
strips need the observed flip and the time since the last turn (tracker field; the pause per state from the FSM
decodes). The sustained-approach case (Reed / Minister closing at p99 idle speed from 0.5-1.0 u, inescapable in the
synthetic test) is covered by the 1.0 u margin plus replanning; recorded idle motion does not sustain it (DistanceFly
keeps them 5.5-9 / 6-7.5 u away).

---

## 4. The planner in v2

### 4.1 What S = 0 means

S(r) = 0 iff all of:
- (i) the row's envelope (bounds_lo, HeroBox) meets no D1 cell over [0, T_r] on its non-invulnerable frames, with G1R
  moves resolved for this row;
- (ii) if the row hits an enemy: its hit branch (counter per row, knockback widening, BODY+ from t_h) is also clear;
- (iii) every pending group-2 attack passes 3.2 (a)-(c) for this row;
- (iv) at every lock-in of the row: from the locked state played out, an escape exists against D1 with the bodies grown
  over the lock's remaining duration + W_r (not just W_r), the BODY+ zones, the pendings, and any G1 family that can
  start inside the lock and reach the hero before the lock ends (start -> first damage from the per-instance table:
  EN_JUMPSLASH 0.400, MI_CHARGE / EN_SLASH / EN_CHARGE 0.483, CM_SLASH 0.500, ...; evades / body moves from 0.017 s);
- (v) at the row's end: the light cone (today's `_light_cone_occ`) against D1 continued past H (G1 and hazards with
  known timing), with the escape test of tier 1.

In words: **the row touches nothing that is already decided, and whatever is still open (a pending aim, a start, the
end of the plan, a lock) leaves the hero a way out that does not cross the decided danger.** S = 0 no longer means "the
row stays out of everywhere an enemy might be within 0.8 s".

### 4.2 FORCED_RISK in v2

When no row has S = 0, rank (after today's hz, hz_soft, U, keep / mkeep keys, unchanged):
1. **certain damage**: masks the row loses to D1 contacts (G1 / G1A / HAZ / body, by the template's damage, 2 for the
   Clapper; multi-hit counted per the Q3 rule), weighted by branch probability only for random branches (combo 2/3,
   JumpSlash 0.5) and for counters (P(counter | hit), gap 3);
2. **latest first certain contact** (t_c);
3. **pending risk**: for rows that fail only 3.2 (b) / (iv) / (v): the expected loss = damage x P(hit | inside the
   zone at that depth), from the validation tables (aim_ics confusion: e.g. the pin's hit share inside the person-
   timing zone 32/172), ranked by the depth into the zone (distance to its boundary, deeper = worse);
4. BODY+ violations by depth;
5. then today's seen / committed-fine keys, eml, J.
Rationale: a certain hit is worse than an open risk; among open risks, the one the game is least likely to land.

### 4.3 The switch and the migration

`SSBOT_FORUM_V2` (default 0; read once at import like the other Forum switches; listed by `zone_overlay` SWITCHES):
- **0**: today's code path, bit-identical (tests lock it).
- **1**: D1 replaces the support (`MultiForecast` builds D1 through a new `V2Support` builder; `occupied`,
  `occupied_split`, `prob` read it); the planner's existing escape check (+n threats reduced to BODY+ families),
  `_pin_contacts` and light cone unchanged. Useful alone: overlay, precision, half-screen, hindsight.
- **2**: group 2 (3.2-3.3) replaces `_pin_contacts` and the "+n" threat list; lock-in checks with D1 terrain.
- **3**: FORCED_RISK v2 (4.2).
Under V2 >= 1 the clip switches (RCLIP, BODYCLIP, TINYCLIP, RTHROW, REANCHOR, NSBOX, WALKFLOOR, PRESTRIKE, TIGHT) are
ignored with one warning line; GATES is read as an input. Products live in `knowledge/1.0.30000/enemies/forum/v2/`
(templates per type `.npz`, `rules.json` with decision states / timing windows / aim rules / branch probabilities /
BODY+ table / body bands, `escape_reduced_<state>.npy`, `blocker_<family>.npz`, `manifest.json` listing each file's
source set, build commit and md5); V2 refuses to run if a listed file is missing or its md5 differs.
Migration: oracle view only at first (vision needs antic-start, facing and decision observations at L 3; the BODY+ and
zone tables must then be re-scanned at L 4-6). HeroBox replaces Bounds in the D1 dilation and in the planner's contact
test under V2 (the top is 0.22 u taller). Default on only after the gates of sec. 5 pass on the clean set; the clip
switches and the not-started walk code are deleted one week after V2 becomes the default with no regression.

---

## 5. Gates

All on frozen checkouts, Idle priority, at most 2 heavy processes of one agent, workers x NUMBA threads <= 8. Truth =
real damage colliders incl. multi-hit dealt 0 / eff != 0, +-1 frame, parked members skipped, dilated by the HeroBox
(say so in every table; report the Bounds number once for continuity).

### 5.1 Hindsight (person and bot, every k 0..12 and 36)

Compared with **base (V2 = 0, RCLIP = 0)**, never with a nested candidate, on own AND all-owner coverage
(`verify/hind_all.py` style), per family and separately for rows with a hit on the enemy within the horizon:
- **H1, decided danger**: real colliders of moves that were under way (or decided) at the origin, and hazards in
  flight: v2's coverage >= base on every row at every k (0 lost rows unless each is explained and accepted).
- **H2, idle bodies**: coverage >= base for k <= W_r (5 frames). For k > W_r v2 gives coverage up by design; report it.
- **H3, escapability (new)**: every real collider at t + k that v2's D1(t) does not cover (all k to 36) must have been
  escapable: at the moment it became observable (antic start + L, decision, body motion start) the recorded hero state
  was outside the threat's inescapable zone computed with the FULL library and D1 as terrain. An uncovered and
  inescapable collider is a v2 miss: 0 allowed on dev, 0 on the clean set; base's all-owner misses are reported
  alongside.
- k36 is inside the planner's horizon (0.6 s); base's own coverage there is 83.9 % (bot), so H1 / H3 at k36 matter.

### 5.2 Committed precision per type (group 1 only; target <= 1.5x)

Ratio = predicted area / real area at k (0 / 6 / 12 / 18), p50 / p90 / p99 and share > 1.5x, per type and per family x
state, two versions: shared D1 (what the overlay shows) and per-row resolved (what S uses). Windows that cannot reach
1.5x on the shared D1, and why (the game decides after the commit, or a random branch):
1. RE_STAB Stab Antic (0.63 s): the start point follows the hero up to 5.45 u; per row it resolves.
2. RE_DEFEND counter before Parry Y Aim: three sectors, until hit + 0.5 s; per row it resolves when Parry Y Aim is in
   the row.
3. MA_SLASH before Slash 1, CM_SLASH before Slash 1 and Slash 4-5: both mirrors (about 2x); per row single.
4. AT_FIRE Fire Ready: side + start +-5-7 u; AT_DEFEND: orbit around a tracking Maestro.
5. CH_SLASH before Combo? (2/3 random) and EN_SLASH before Combo? (JumpSlash 50 %): branch unions (1.5-2x).
6. EN_CHARGE end point (shared bound to the wall); spear homing cone.
7. CB_THROW release point (body 0.94 / 0.47 u p95 before release) + vx jitter +-1 u at landing.
8. MI_CHARGE angle tail (p95 27 deg, C7); MI_PARRY Parry Block residual 4.9 u (gap 2).
9. CC_SLAM collider switch jitter +-3 frames (back edge 3.8 u p95): expected to drop with the Slam 0 re-anchor;
   otherwise listed.
10. Hit branches (knockback widening) and the counters of the rows that hit: conditional by nature.
Everything else must reach <= 1.5x at k12 per row and per type. Bodies are not "committed" and are reported apart
(the person's frame 2916: Choristor Battle Idle 43 u2 against 6 u2 real today; v2 expects about 7-8 u2).

### 5.3 Half-screen

`tools.zone_share` k0 and k12 on the person's three sessions and the bot's waves (all waves, not only w0): list and
plot frames over 50 %. Target 0 frames at k0 and < 5 % at k12 (base 44.9 / 70.2 %, s3cand0 4.77 / 35.1 %).

### 5.4 Re-score per type

`forum_human_rescore` on the 32 segments: misses support-alone and escape-filtered must not rise in total or for any
type against the truth-fixed base (s1rb_base_1b8c69a: 1 miss, a pin). The 5 pin rows of C12 must be unsafe under
V2 = 2. FORCED_RISK share and safe ticks reported.

### 5.5 Recall at latency, availability, timing

- multi_recall v2 = H1 + H3 at L 2, 3, 4.
- Availability: share of ticks with a safe row, base vs V2; share of rows rejected only by tier 1 / 2 of 3.3 that a
  full-library offline audit clears (reduced-library cost).
- Timing: tick p50 / p99 per fight (Forum target: median of per-fight p99 <= 15 ms; V2 adds <= 2 ms p50 / 5 ms p99),
  late frames per fight.
- Tests: V2 = 0 bit-identical; synthetic D1 contains the recorded colliders of the template's own instances; the
  reduced library never clears a cell the full one does not; refusal on a missing product.

### 5.6 The clean held-out set

Nothing recorded so far is clean for v2's purpose: R0 dev fits v2; R0 fresh is clean for v2 tables (they come from dev
only) but small (35 fights); R2 and R1c fed RCLIP and the classifiers (ground used R1c); the person's sessions and the
2026-10-08 Forum_W runs were used as truth in diagnoses. So:
- **What**: full Forum runs (waves 0-12) recorded after 2026-10-09 on one frozen checkout, 60 fps, 1.0x speed, Forum_W
  loadout, oracle export with every collider (incl. dealt-0 multi-hits), allies exported.
- **Policy**: two policies, so the hero visits the states the zones depend on:
  - A: the current default planner (V2 = 0), 60 fights: the distribution the earlier gates used.
  - B: the same planner with 20 % of ticks replaced by a random allowed row from the candidate set (keeps the bot alive
    while visiting low air, no-dash and close-range states that A avoids), 40 fights.
  - Plus every new session of the person, reported separately as "person-clean".
- **How many**: 100 fights. R0 dev's 107 fights gave about 600 Minister counters and 2,078 Reed stabs; 100 fights give
  >= 1,000 instances of every frequent family and a few hundred of the rare ones (counters, CC_EVADE facing away stays
  rare: 4 / 7914, so it is certified by the scan, not by the set).
- **When / cost**: needs a game instance and the person's consent (focus-stealing; the person's slot 08:00-08:30 PDT
  for deploys); about 6-8 min per full run, 3 instances in parallel overnight = 4-5 h.
- **Hygiene**: a `CLEAN_DO_NOT_FIT` marker in the set's root; the product builders refuse any path under a marked
  root; the manifest of every v2 product lists its sources.
Start recording this set as early as possible: it does not depend on v2 and is on the critical path to default-on.

---

## 6. Development plan

Cost basis: recent rounds cost about 0.5M subagent tokens per 1 % of the weekly quota. Weekly use was 66 % at this
pass (reset 2026-10-15 10:00 UTC). Each round ends with an adversarial verifier (included in the estimate), freezes
its checkout, and leaves every default unchanged.

| round | content | safe because | useful alone | tokens | weekly % | machine |
|---|---|---|---|---|---|---|
| V0 facts | One idle-check protocol (aim_ics fc31849 kernel, HeroBox, full library for every "inescapable" claim, L 2 / 4, walls and blocker variants, hero states incl. vy bins) re-run on the breakers and the marginal cases; resolve C2, C3 (facing-away per family from the FSM turn pauses), C6, C7, gaps 1-3; per-instance timing table (replaces strikes.json minima). Output `v2_facts.json` = the table of sec. 1 as data | no planner change | corrected facts, BODY+ table, decision table | 3-4M | 6-8 | 2-4 h Idle |
| V1 D1 offline | Template builder (node chains, decision anchors, kinematic split + terrain clamp, branch unions, per-bin per-side 2-fold margins), body-band table, hazard paths, G1R bounds and resolvers (pure functions), manifest; offline D1 auditor computing H1 / H2 / H3 (first version, coarse library) and precision per type on R0 fresh and the seen sets | no planner change | shows whether 1.5x and full H1 are reachable before touching the planner | 5-6M | 10-12 | 4-6 h Idle |
| V2 support | `V2Support` in MultiForecast behind `SSBOT_FORUM_V2=1`; overlay layers (body / body+ / g1 / g1a / g1r / hazard); tests (V2 = 0 bit-identical); gates 5.1-5.5 on seen + R0 fresh; replay of 20261009_085824 for the person | switch default 0; the old escape check and pin check still run | the person can watch v2 zones in replays; precision and half-screen known | 4-5M | 8-10 | 6-10 h Idle (gates) |
| V3 group 2 | Decision tracking in `EnemyTracker` (decision states, windows, per-row inputs); per-row resolvers in the planner; reduced libraries (greedy cover) and blocker tables; D1 raster; tier 0-2 kernel; `SSBOT_FORUM_V2=2` replaces `_pin_contacts` and the "+n" threats; pin regression rows; bench | switch default 0 | pin / spear / Clapper jump / Reed stab / side moves checked exactly; escapes respect other enemies | 5-7M | 10-14 | 6-10 h Idle (blocker scans + gates) |
| V4 ranking and locks | Lock-in checks with growth over the lock, FORCED_RISK v2 (`=3`), re-score per type, timing | switch default 0 | fewer and better-ranked forced ticks | 2-3M | 4-6 | 3-5 h Idle |
| V5 certification | Gates on the clean set (100 fights) + person-clean; verifier; decision memo for default-on | gates only | the default-on decision | 3-4M | 6-8 | recording 4-5 h (game) + gates 6-8 h |
| total | | | | 22-29M | 44-58 | |

Order and budget: V0 and V1 (8-10M, 16-20 %) fit before the 2026-10-15 reset only if the quota beyond 70 % is opened
for them; otherwise V0 now (it is small and unblocks everything), V1-V2 right after the reset, V3-V5 in the following
week. The clean-set recording (5.6) can run in parallel with V0 / V1 as soon as the person allows a game instance.
Round independence: V0 and V1 change no code path; V2-V4 each add one switch level whose lower levels stay usable;
V5 changes no default by itself.

---

## 7. Open questions for the person

1. BODY+ for the Reed and the Minister is 1.0 u around the body (re-measured in V0). Acceptable, or should the dash
   state be split (a smaller zone while dash is available)?
2. The clean set: may the bot record 100 Forum runs (two policies) overnight, and when?
3. FORCED_RISK: is "a certain hit is worse than any open risk" the right order, or should a deep pending zone (e.g.
   under a Bellbearer about to evade) rank with certain hits?
