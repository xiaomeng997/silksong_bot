# HANDOFF - M2 integration (branch m2-integration-6)

## START HERE (2026-10-12): Forum Clapper 1v1, the next session

Written by the session of 2026-10-11/12 for a fresh session (the old one's context was too long). Reply to the person
in Chinese; code, commits and this file in English.

### Update 2026-10-12 evening (session ae67fe04): live results, read this first

- Dev branch head `effdf6d` (frozen `C:\ssbot\live_1v1_effdf6d`). Since 677979c: G1 the general special rule
  (SSBOT_FORUM_SPECIAL_MODE, real-box approach check on by default), G2 small runes (5 switches), G3 delayed / chained
  down slashes (SSBOT_FORUM_DSLASH), G4 HITS_FIRST / SPECIAL_KEEP / MOVE_HITS / table v2, two reviews (15 fixes).
  All default off; switch-off identity with 677979c proven. Branch HANDOFF sections G1-G4, forum.md 49-54.
- Live Clapper 1v1 (instances 0/1, 2026-10-12 19:06-19:41, manifest `C:\ssbot\sandbox\1v1g_manifest.txt`,
  collect `C:\ssbot\data\m2_live_g\col`, summary `s2.json`):
  - fcs 24 eps: 22 kills, 7 hitless (29 %), 34 hits (30 not slam: rune bombs), 0.41 landed hits/s, kill p50 54 s.
  - **rn 16 eps: 16 kills, 15 hitless (94 %), 1 hit, 0.60 hits/s, kill 34 s; rn35 8 eps: 8 kills, 8 hitless, 0.57/s.**
  - The special mode and the down-slash family are harmful live: allns (runes + family) 5/8 kills, 0 hitless, 7 slam
    hits; gsav2 (special mode only) 4/8, 12 slam hits; allkh (all, old table) 4/8, 15 slam hits; allv2 1/3.
    One trace (run 20261012_190851 ep 0, f 20914-20958): a family jump took the hero up as the slam antic began, L2
    held 'slam: strike', the planner changed plans every tick, she floated in front and Slam Collider 1 hit her.
    The open-loop replays could not show this.
- Next (the person decides): make the rune switches default (rn vs rn35); the person's eye check of the per-bomb
  forecast (`start_overlay_rune_check.ps1`) is still owed; a 0.5x demo with rn. Then, after the weekly reset (Thu
  10:00 UTC; 97 % used on 10-12): diagnose the special mode / family slam hits from these live logs; G4's undone
  part (follow-up theory to k 77, end state, approach plans per window); the person's later rules in the plan doc
  of 2026-10-12 (keep vs extension, keep for all rows, DPS ranking over one common window).
- Game instances 0 and 1 were left open (launched 19:00); DEMO_SOON is back in place.
- The special module is to be REBUILT as a general module (the person, 2026-10-12 late evening; plan doc notes from
  "why it jumps too early" on): per (enemy, move) a space-time grid (frame x position; no horizontal inertia, extra dims
  only for dash / sprint; air slices by frames since takeoff x jump hold), the enemy's boxes per frame, the strike
  regions drawn in, backward reachability with scores (strike cells: depth + follow-ups; paths: discounted strike
  score + clearance), stored as score contours (MATLAB-style ring matrix, ring tree, CCW outer / CW holes, binary
  search on the level, compressed so no lattice point changes side on the feasibility ring and +-1 level inside);
  online: one-step lookahead over the inputs with a per-key-change cost added at search time. Live demos showed why
  the current special mode fails (8720b7a, arm rnv2nd: the special row drops out of its per-tick re-check every
  other tick and FORCED_RISK presses a jump ~20 frames early). 8720b7a also adds SSBOT_FORUM_CL_NODOWN.

### Where things are

- Code: branch `worktree-wf_f1846551-5f9-1`, worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_f1846551-5f9-1`,
  head `677979c`, NOT merged to main. It holds planner v2-lite and everything after it (stages S1-S3, T1-T3) plus two
  commits of the old session: `42d258d` (SSBOT_FORUM_KILL_FREE, default on: no killing-blow hold-back for the death
  slow motion's missing pause, the person's rule) and `677979c` (the combat_run worker boosts itself: High priority,
  P-cores 0-15, power throttling off).
- That branch's HANDOFF.md has the detailed sections "Task 1v1" S1-S3 and T1-T3; the facts are in
  `docs/facts/1.0.30000/forum.md` sec. 43-48 there (Chinese).
- The person's rules and decisions: `docs/plans/forum_planner_plan.md` on main. Read its notes of 2026-10-09..12 first.
  The newest ones are the special-move table design, the experiment method, the two-Clapper / finale tactic (T4), the
  "why" study and its fix order, and the general special rule.
- Data: `C:\ssbot\data\m2_pogo` (T1, down slash on the slam), `m2_specials` (T3), `m2_two_clapper` (two-Clapper data
  checks), `m2_why` (the 2026-10-12 replay study; `refute/table_q1.txt`, `table_q2.txt`), `m2_1v1*` (1v1 runs),
  runs in `C:\ssbot\data\runs\m2\2026101[12]_*`.

### State of play (Clapper 1v1, Forum_W_w7, fo_cl_w7w, crest Wanderer)

- With the worker boost, the arm fcs at 677979c: 7 of 8 kills, 10 hits, 7 of them small rune bombs, kill 44-59 s.
  The old code f2e30f9 (arm tj2) boosted: 3 of 3. Without the boost, the evening runs had 10x the late states and
  0-2 kills of 6.
- The bot glides away from the small runes, never down-slashes the slam and stays far. The 2026-10-12 replay study
  explains why (plan doc note "why it glides / never down-slashes / not in the face").
- T1: the down slash on the slam, theory vs live 85.6 %. The person's strike (antic frames 45-50, 3-6 u in front)
  succeeded 57/60.
- T3: the special table specials_CL_SLAM.json has 5,757 entries. Arrive-and-strike rows sit behind
  SSBOT_FORUM_SPECIALS=1 (off by default). Every special row has been rejected so far.

### Next task (the person approved it; budget: about 2-3 % of the weekly quota)

1. Implement the person's GENERAL SPECIAL RULE (plan doc 2026-10-12):
   - At the antic of a move that has table entries (CL_SLAM first), and when a strike point is reachable and safe from
     the OTHER enemies (the strike frame and the bounce path after it), the enemy goes into "special mode":
     - drop that move's attack-range estimate and its aim zones from the safety check;
     - keep the enemy's body;
     - keep every other enemy's prediction.
   - A down slash on an enemy in a move is a certain hit: from the press frame check only the bounce branch, in stage
     1 and in the envelope. Its escape starts from the bounce state.
   - The approach before the press is checked against the body and the other enemies only.
   - The strike can lie beyond the 0.6 s horizon (slam antic 0.8 s, press at frames 42-50). So the strike point is a
     goal for the L2 controller / the arrive-and-strike rows from the antic's first frame.
   - L2 must stop sending the hero 13 u away at a slam (gauntlet.py _clapper_spot / CC_RETREAT). Give hit_w > 0 at the
     strike cell.
   - Special rows: filter them on the keys they actually use, not ctx.allowed_mask.all().
   - With no safe, reachable strike, fall back to the normal dodge.
2. Small runes: before Cast 2 is seen, treat the bombs as not started. Open-loop effect: Cast 1 umbrella 25 % -> 4 %,
   slashing 18 % -> 91 %.
   - Then stand on the ground 3-4 u from the Clapper during casts (face_u A/B).
   - Add the person's row: continuous slashes plus a short hop just before ring 1 lights, with no second jump press in
     the air (that opens the umbrella).
   - Per-bomb timing with a small bomb margin.
   - Prefer non-glide rows.
3. Live A/B on the Clapper 1v1 against fcs: hitless %, landed hits per second, kill time, hits by source.
4. Then show the person:
   - the eye-check overlays (prepared, not started): `C:\ssbot\sandbox\start_overlay_pogo_check.ps1` and
     `start_overlay_specials_check.ps1`. They wait until no game window is open; launch them via WMI.
   - a 0.5x demo.

Later, from the plan doc:
- T4: the finale with the person's two-Clapper tactic.
- Bell Beast with the special table (the person, 2026-10-12: "surely much faster than before"; after the Forum, route bosses are parked). Today: oracle view kill p50 58-59 s, 0.95-0.97 down-slash hits per charge; vision view (degraded_dust) kill p50 95-99 s, 0.15-0.22 per charge (the certain_boss gate); Dig In / Charge End / Leap Land down slashes 0 accepted (m2_vision_view.md sec. 3, 5). Under vision the cells must be robust to the view's position / timing noise.
- Cross Stitch test (add it to a Forum savestate).
- Reed 1v1: the stab antic motion; 90 % of ticks over budget.
- Verify the planner's own input lag (T3 found the probe one frame late).
- The new vs old code regression is still open under the boost: old 3/3, new 3/3 + 7/8.
- Occasional 1.4-3.2 s worker stalls trip the brain-lost watchdog (HARNESS_FAIL). Cause unknown.

### Operations

- Live runs: `C:\ssbot\sandbox\1v1_live.ps1 -Rev <sha> -Inst <0|1> -Arms <arm> -Chunk N -Blocks 1 -Seed S
  [-Manifest ...]`. Arms are in `1v1_arms.txt`. Frozen checkouts come from `1v1_freeze.ps1 -rev <sha>`
  (C:\ssbot\live_1v1_<sha>).
- Start everything detached via WMI `Win32_Process Create` (PowerShell `Invoke-CimMethod`).
- C:\ssbot\sandbox\DEMO_SOON pauses live runs: rename it to DEMO_SOON.paused for a run and back afterwards.
  STOP_AGENTS stops agents.
- Game instances: `brain> ..\scripts\uv.cmd run python -m ssbot.tools.launcher -n 2 --detach`. NEVER `--restore`,
  NEVER kill game processes (ask the person to close the windows); NEVER deploy the oracle.
- At the time of writing, instances 0 and 1 are open (started 05:08 on 10-12). The next launcher prunes them and
  restores the golden PlayerPrefs.
- Workers boost themselves from 677979c on. With an older checkout, run `C:\ssbot\sandbox\boost_workers.ps1` alongside.
  Offline long jobs stay at Idle priority, at most 3-4 at once.
- Known test failures, both from before this session:
  - `tests/test_three_layer.py::test_a_bell_in_reach_is_a_hit_target_of_weight_0`;
  - `tests/test_import_firewall.py` (from S1).
- Budget: weekly 91 % on 2026-10-12 06:00 PDT; it resets Thu 2026-10-15 10:00 UTC. About 0.5M subagent tokens ≈ 1 %.
  The person wants one agent at a time and about 1-2 % kept for chatting until the reset.
- Workflow scripts must be ASCII only. Never SendMessage to a running workflow agent; use a note file in its data
  directory.

One section per merged chain; each keeps its chain's own text (headings demoted one level) including its Next steps.
Paths to worktrees / run dirs in a section are that chain's, not this integration worktree's.

## Integration (branch m2-integration-6, worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_510ef709-004-1`)

Main (3744eeb, docs only since 03482a4) plus five chains, one `git merge --no-ff` each, in this order: R route research
(worktree-wf_c0d56d51-4cb-5), W kinematics (worktree-wf_946a7803-63c-3), F Forum (worktree-wf_946a7803-63c-2), H pause /
quit (worktree-wf_c0d56d51-4cb-4), V vision view (worktree-wf_946a7803-63c-1). Main's later doc commits are merged too:
94bff53 (DESIGN 3.6.4, at the end of the integration, 5f6c5e0) and, in the fixer round, e1edd86 (DESIGN Q1 / Q1a user
rule) and 3b70280 (formal run keeps Steam achievement notifications), so the branch holds main up to 3b70280. Offline
only: no game instance touched, nothing running, nothing deployed.

### Conflicts and how they were resolved

- `train/encounters.py` (W x F): both kept - W's `BELL_BEAST_REAPER` and F's `FORUM` + arms; `ENCOUNTERS` lists all
  seven; `forum_variant` uses the module-level `replace` import.
- `train/episode.py` (F x H, post-kill zeros): F's `act_after` (policy flag or a gauntlet encounter) decides; the kept-
  acting tick goes through H's `_act` (ACTION flags from the policy).
- `safety/supervisor.py` imports (H x V): union of both sides' names.
- `train/supervision.py` (H x V): `SupervisedControl.step(s, obs=None, ws=None, inflight=(), **planner)`. In the vision
  views the supervisor and the pause machine read only the delayed view (V's rule: `vision_cues_from_state(obs)`,
  `input_from_world(ws)`); H's key guard then sets `cues.keys_clear` from the current STATE's `act.hf` and the in-flight
  masks in every view. Decision: the key path is the bot's own output (the final inputd sink holds the same filter
  state), not an observation of the game, so reading it undelayed does not break the vision rule. Test:
  `test_vision_mode_keeps_the_menu_key_guard`.
- `train/planner_policy.py` (H x V): every `sc.step` call passes V's `obs` / `ws` and H's `inflight`; V's unpredicted-hit
  backlog kept in the pause tick; H's `action_flags` kept.
- `tests/test_supervision.py`: both chains' new tests kept. `HANDOFF.md`: this file (one section per chain).

### Fixes after the merges

- `tests/test_episode_post_clear.py` (F's fake link had no `flags` argument, so H's `_act` raised and 5 tests ended
  HARNESS_FAIL): test fake only.
- `combat_run.new_run_dir`: `<timestamp>_<encounter>_<tag>`, `_2`, `_3`, ... when that name is taken (mkdir is the claim;
  the 2026-10-03 07:45 FileExistsError). Names without a collision are unchanged.
- Oracle EXCLUSIVE (H's 10d3948, still NOT deployed): `HoldFilter.QueueExclusive` spares the keys an earlier EXCLUSIVE
  ACTION of the same stretch asked for (the pause loop's own taps keep the 2-frame minimum press); a plain ACTION ends
  the stretch; the brain-lost Pause tap still cuts every key. InputLogicCheck `ExclusiveSparesTheLoopsOwnKeys`, all ok;
  `dotnet build oracle/SsOracle.csproj -p:Deploy=false` ok. The merged `oracle/` = branch oracle-deploy-20261003
  (2783573) + H's input / IPC files + this fix, nothing else.
- `docs/facts/1.0.30000/crests.json` (P17) committed; `.gitignore`: `/knowledge/1.0.30000/enemies/forum/*.npz`.
- Fixer round (after the verifier): main re-merged (doc only, clean). Oracle: KeyboardInjector's ways into the filter
  are HoldFilter methods now, so InputLogicCheck runs the same calls: `TryQueueMask` = `QueuePlain` (EndExclusive + the
  two Pushes), `SetMaskExclusive` (brain-lost Pause tap) = `QueueExclusiveCutAll` (EndExclusive + QueueExclusive; the
  mask is validated first, so a rejected request no longer ends the stretch). New check `InjectorExclusiveWiring`
  (same-stretch key spared; a plain ACTION ends the stretch; the brain-lost Pause cuts the loop's own key); ALL OK,
  `dotnet build -p:Deploy=false` 0 warnings / 0 errors, not deployed.

### Checks (offline, below-normal priority, NUMBA_NUM_THREADS 4; scratch outputs in this session's scratchpad)

- Full suite (`python -m pytest -q tests`): 878 passed, 1 skipped, 1 xfailed, 1 failed:
  `test_hitbox_tables::test_support_query_budget_on_the_committed_bell_beast_templates` (p99 3.85 ms vs the 3 ms
  budget: the known failure under the machine's load; budget not loosened). Before the test fix above: 6 failed (that one
  + the 5 merge failures).
- InputLogicCheck (oracle input logic): ALL OK, incl. the new own-key check and (fixer round) InjectorExclusiveWiring.
- Fixer round: no Python change since 5f6c5e0 (the main merge is docs only); test_primitives (parses DESIGN.md),
  test_key_guard, test_supervision, test_supervisor: 54 passed.
- (a) Held-out support recall (`support_recall 20261001_122249_BellBeast_data --recordings=i2_002,i3_002 --table
  C:/ssbot/data/m2_heldout/tables --lags=2,3,4 --margin 0`, 35 fights): ve_dust noise seed 7 23,896 / 23,896 and oracle
  23,896 / 23,896 at lags 2, 3 and 4 (V: 23,896 / 23,896).
- (b) kin_check Hunter (default params and lanes) on 20261002_171806 i0_000, integration vs main's code (exported tree of
  3744eeb): the two JSON reports are identical except the params path (all five settings, all categories, the 40
  worst windows). Forum held-out (`--params hero_reaper_forum.json --lanes bounds_lo_mix --bounds-events none`) T1
  s98600 99.448 % (32,953), T2 s98700 98.895 % (16,747), together 99.26 % of 49,700; every category as in
  movement_kinematics.md 5.3 (dash 97.34, glide 98.125, contact 89.78, slope 98.36, wall 100, scramble 99.48 %).
- (c) planner_bench, 20261003_053033 i0_000 (degraded_dust live run), 8000 frames, threads 4, warm numba,
  integration vs V's branch: decisions identical (forced share 0.2138 ve / 0.0405 oracle, same mode counts). The
  integration is SLOWER, measurably: the verifier's 4 pairs (both views, both orders) had the integration slower in
  every pair - tick p99 +1.00 / +0.60 ms (ve: 14.73 vs 13.73, 15.03 vs 14.44) and +1.25 / +0.96 ms (oracle: 15.83 vs
  14.58, 15.63 vs 14.66), tick p50 +0.43 to +0.73 ms, rollout phase p50 2.39-2.41 vs 1.97-2.07 ms, p99 4.20-4.30 vs
  3.65-3.86 ms (paired: rollout p50 +0.33-0.42, p99 +0.43-0.55 ms). The integration report's "tick p99 within noise"
  did not reproduce. Cause: W's Hunter kernel, not the conflict resolution (kinematics.py / kin_jit.py are W's files plus V's two
  np.require hunks). Fixer profile on the planner's own main rollouts (442 sequences x 49 frames, bounds lanes, 250
  captured calls, min of 7 replays, alternating trees): compiled kernel 1 thread 4.83-5.15 vs 4.19-4.51 ms (+12-20 %),
  4 threads 1.40 vs 1.15 ms; Python-side preparation +0.02 ms; the lanes run per sequence (3 of 9) and the inputs
  (masks, terrain, lane runs) are identical. Compiling the Forum loadout branches out for abilities == 0 (the abilities
  word a constant 0 in a second copy of the frame loop, inline and as a separate function; Hunter outputs bit-identical)
  gained nothing measurable (5.09 / 5.11 vs 5.13 / 5.15 ms) and doubled / tripled the first compile (51 s -> 97 / 157
  s), so it was not kept; W's four extra modes in `relinq` cost ~3 %. The rest is spread over W's larger state (K 51 ->
  81) and parameter row (67 -> 151 columns); not changed.
- (d) Forum gauntlet tables rebuilt from the 13 complete gauntlets (223640, 230325, 231917; `behaviour_build --encounter
  Forum --allow-failed-validation --out <scratch>`, 986 s): coverage.json identical to the committed one except code sha
  / paths; every table JSON identical except build time / sha; all nine _hitboxes.npz byte-identical to F's. 28,029
  contacts, unattributed 0, held-out beyond R_FAIL as forum.md section 11 (Clawmaiden 66 / 1258, Reed 92 / 3104, ...).
- (e) tests/test_key_guard.py passes; pause_stress on 20261002_232051 (100 trials: special 52.5 % / 43.4 % without menu,
  99 / 99 paused + main menu, latency p50 2 / max 3, 0 game keys on the pause frame or in menus, 0 unintended unpauses,
  0 wrong submits) and 20261003_001326 (93 trials: 49.5 % / 38.7 %, 93 / 93, max 3, all zeros) - output identical to
  H's own runs of the tool.

### Next (integration)

1. Landing in main: the main checkout has an untracked `docs/facts/1.0.30000/crests.json` at the path this branch now
   tracks (4ff6046), so `git merge m2-integration-6` there aborts ("untracked working tree files would be
   overwritten"). Move that file aside first: it is the committed file with CRLF endings, nothing is lost. Merge main
   into this branch again first if main has moved past 3b70280.
2. Deploy (lead): the oracle in this branch = deployed 2783573 + EXCLUSIVE (with the own-key fix and the wiring moved
   into HoldFilter). Stop instance 4's pause campaign before (it holds SsOracle.dll). After deploying, the key guard
   could model EXCLUSIVE (H's note); the post-deploy pause campaign is the live check of the KeyboardInjector side.
3. Planner cost after W's Hunter model: tick p50 +0.4-0.7 ms and tick p99 +0.6-1.25 ms against V's branch in
   planner_bench (rollout phase p50 +0.33-0.42 ms, p99 +0.43-0.55 ms); decisions unchanged. Compiling the Forum
   branches out does not recover it (Checks (c)). Watch late ticks in the next live vision run; if they rise, profile
   the frame loop itself (state size, relinq) - the Forum branches are ruled out.
4. DESIGN Q1 / Q1a changed after the chains were cut (e1edd86, user rule): h <= 1 -> quit in the post-hit window
   (pausable from ~0.25 s after the hit, i-frames to ~1.2 s), no Bind attempt; h <= 1 not caused by a hit (frost,
   pending damage) quits at the first pausable frame; h >= 2 and HP < max -> heal first (Bind in place when the Bind
   commit conditions hold, else at a verified safe spot, else keep fighting under Q3 / Q6). Check Supervisor against
   it: `_triggers` Q1 fires at h <= 1 (and H's UNBOUNDED case against the worst known event) without a post-hit-window
   rule, and `Restrictions.heal_first` is set only in YELLOW / RED (`careful`), not for every h >= 2 below max HP.
   This replaces the 10-02 revision (heal first even at h <= 1) that M2.md recorded before.
5. The chains' own next steps follow below.

## Chain R - Forum route research (branch worktree-wf_c0d56d51-4cb-5)

Original title: HANDOFF - Task R (Forum route research, offline)

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_c0d56d51-4cb-5`, branch `worktree-wf_c0d56d51-4cb-5`.
Finished normally (no stop). Offline only: no game instance used, no job running.

### Done (committed)

- `docs/research/forum_route.md` (Chinese): Ascendant's Grip (Jubilana's shop in Songclave, 350 rosaries, after the
  "Save City Merchant" wish + Song_07 ambush), Reaper chapel (Greymoor_07 -> 20b -> 20c, 4-wave gauntlet, shrine
  needs 3 Binds, AutoEquipCrestV2 strips non-skill tools until a bench, respawn set to the chapel + autosave, ~8-9 s
  pause disabled), G&Z chain (Greymoor_05 forced first meeting, roof shortcut lever in Library_09, garmondInLibrary
  only via TimePasses, spar 460 HP, garmondWillAidInForumBattle via the FSM variable override, Hang_06 recruit),
  LoadedFromMenu call chain (Continue / new game only) and re-recruit, Cogfly (Hang_09, 1 Tool Metal, 0 rosaries,
  8.3-9.3 s no pause), Reaper slots and conflicts (Grip vs Weighted Belt, lockets per crest), time estimates (gate
  distances + pace from the human recording), DESIGN 3.6.4 / 3.6.5 (+3.5.7 / 3.7.5) edit proposals, open items.
- Fixer pass (same day) after the verifier round:
  - Songclave prerequisite (new section 1.1): the wish board, Jubilana and the Songclave RestBench are children of
    "Enclave States/States/Level 1", active only at enclaveLevel >= 1. 0 -> 1 happens only in TimePasses outside
    Song_Enclave and Bellshrine_Enclave with metCaretaker; metCaretaker comes from the forced Caretaker cutscene,
    which exists only after the Songclave bell (bellShrineEnclave). The bell-tower Bell Bench appears after ringing
    and is an equally close TimePasses option for garmondInLibrary at S21. Grip times, S18/S20/S21 proposals and a
    route_check assertion updated.
  - G&Z lethality: WildSlash Hero Damager 5's second DamageHero (flags 0) analysed in code (HeroBox uses the first
    component; the clash path is per component but deduped via PreventDamage/HasBeenDamaged) - probably harmless,
    not proven, treated as lethal; rule "at 1 mask every G&Z hit counts as lethal".
  - Hang_06 visual rule restricted to "on entering the scene"; recruit state read from the dialogue key
    (GARMOND_AID_READY = recruited; MEET_FORUM / REPEAT + REQUEST_AID = not recruited).
  - LoadSceneSingleCustom removed from the LoadedFromMenu paths (it never calls BeginSceneTransition).
  - "Talk to Garmond twice at S11" dropped (net zero; Moorwing branch can pre-empt TALK1).
  - Group A time given per case: 4-7 / 7-12 / 4-9.5 / 7-14.5 min.
  - Reaper slot table now cites crestitems.bundle directly (fx_crest_slots.py), not the untracked crests.json.

### Scripts / raw outputs

`C:\ssbot\sandbox\forum_route_scripts\` (UnityPy scripts run with the scratch venv
`C:\Users\Meng\AppData\Local\Temp\claude\C--modeling-silksong-bot\99d0a17d-64d3-4738-80f4-0ed168134124\scratchpad\venv\Scripts\python.exe`;
`pace.py` runs with `..\scripts\uv.cmd run python` from brain). Fixer-pass files start with `fx_`.

### Next (for the lead / a live agent)

1. Live checks listed in forum_route.md section 8 (Continue clears garmondAidForumBattle and Garmond reappears in
   Hang_06; Reaper shrine sequence; Stun Box and WildSlash 5 lethality via LethalBlock would_die; Hang_09 mite reach;
   caravan bench in S11; Songclave bell -> Caretaker -> enclaveLevel 1 sequence).
2. Merge the DESIGN proposals (section 7) after K1 decides Reaper / Grip; check whether the S18 route rings the
   Songclave bell.
3. `docs/facts/1.0.30000/crests.json` (P17 output) is still untracked in the main checkout; the research doc no longer
   depends on it (it cites the asset bundle), but the lead may want to commit it.

## Chain W - Forum kinematics, Reaper attack shapes, coverage map (branch worktree-wf_946a7803-63c-3)

Original title: HANDOFF — Task W (Forum movement kinematics, Reaper attack shapes, safe-pocket tool)

Round 3 (fixer) finished normally 2026-10-03 ~09:30 local. Worktree
`C:\modeling\silksong_bot\.claude\worktrees\wf_946a7803-63c-3`, branch `worktree-wf_946a7803-63c-3`. Everything is
committed; no job of mine is running (instance 3 idle, input released). Detached worktrees I made and can be removed
with `git worktree remove`: `C:\ssbot\live_kn_d4ffef8` (recorded the held-out runs; numba warm) and
`C:\ssbot\kn_hunter_ref` (main f329afb, for the Hunter bit-identity check). `C:\ssbot\live_kn_7a56ead` is round 2's.

Facts: `docs/facts/1.0.30000/movement_kinematics.md` (1.7 terrain thunk, 1.8 slopes / ceiling contact, 1.9 wall
landing, 1.2 / 1.3 / 1.4 / 1.4b updates, 3 polygon frames, 4 coverage map, 5 fit / dev / held-out acceptance, Reaper
audit correction, lane choice, 6 bench).

### Done this round (review findings of round 2)

- Held-out acceptance redone: model frozen at f6c75de; fresh runs recorded first (from d4ffef8, never read before the
  freeze) and evaluated once: `C:\ssbot\data\runs\m2\kn_excite_forum\2026-10-03\TRAIN\kn_excite_forum_s98600` (wall,
  220 trials) and `..._s98700` (floor, 180 trials). B / D are now called the dev set.
- Acceptance definition fixed (decision-time information only): `kin_check --lanes bounds_lo_mix --bounds-events none`
  (no logged contact events: the empty room has nothing for a threat layer to announce), slope windows and mantle
  windows ("locked", Forum parameters) counted. Covered: fit 99.06 %, dev 99.08 %, held-out 99.26 % (wall run 99.45 %,
  floor run 98.90 %); held-out dash 97.3 %, glide 98.1 %, contact 89.8 % below 99 % (facts 5.3 has the diagnosis).
- Model (Forum only; Hunter rollout bit-identical to main on 40 000 frames of 171806 i0_000, all settings): side / up
  slash terrain thunk (AB_THUNK, rows ATK_KIND / ALT / ALT_T / ATK_PDIR, slash polygons in the parameter tail), sloped
  edge collision + roof CancelJump + ceiling late contact (AB_SLOPES, slope_contact 0.005), scramble roof ray at
  Scramble Up's OnEnter and REPEAT DASH from Scramble Up, scr_roof_t 0.0835 (fit bug: entry frame counted twice),
  rpr_thunk_* refit on the fit runs only, glide Bump phase, wall-contact landing (CheckTouchingGround 0.16), estimator
  wallUnstickSteps / wall-jump chain / skid mode / thunk test with two steps, Sprint Grace from Start Sprint (wrong,
  see Next 1).
- Lanes: new `bounds_lo` (bounds + one lane at the limiter's frame time) recommended for the planner (Hunter 97.92 %
  at hull p95 0.020 u vs bounds_ft 98.06 % at 0.348); `bounds_lo_mix` (+2 mixed-phase lanes) used for the Forum
  acceptance figure, same held-out number as bounds_lo, 1.9 x the cost of bounds.
- attack_hit_audit: a hit on the hero ends the swing; Reaper normal 100 / 0 / 3 (the 22 "boss does not take hits"
  FPs were swings cancelled by the hero being hit before frame 5). attack_table_build: live polygons in the rendered
  transform's frame (all samples rigid, 0.000 u); reaper.json up slot back to the dump polygon.
- coverage_map: conservative raster (outline supercover, edge / 2-point colliders, capsule arcs pushed out, the
  oracle's circle octagon instead of a circle around its first vertex), consecutive-frame sweep, hidden entities.
  Bell Beast pockets: left door 1.44 u, right door 1.59 u (were 1.91 / 0.34, both from the circle fix).
- Provenance: `kin_fit_forum.HAND_SET` writes a source entry for every hand-set Forum value.

### Needs the lead

- Oracle deploy (unchanged from round 2): `slash.dump` `paths` (commit 572f0e7, built `-p:Deploy=false`), then on
  instance 3 from this branch: `..\scripts\uv.cmd run python -m ssbot.probes.kin_excite_forum --instance 3 --savestate
  kn_forum_floor --x-safe 33 63 --random-dir --seed 98420 --trials 0 --attack-frames 40 --attack-kinds
  "reaper_attack,dash_attack"`, then `attack_table_build --crest Reaper --live <A>/attack_frames.jsonl
  <s98400>/attack_frames.jsonl <s98410>/attack_frames.jsonl <new>/attack_frames.jsonl` and re-run
  `attack_hit_audit C:\ssbot\data\runs\m2\20261002_225836_BellBeastReaper_data --crest Reaper --instances 3 --slack 0`.
- Planner integration (later round, planner.py not touched): use the lane set `bounds_lo`; the Forum model's nominal
  rollout costs ~2.5 x Hunter's (facts 6).

### Next (in order)

1. Sprint Grace timer: read hornet_sprint's Sprint Timer action (UnityPy venv:
   `C:\Users\Meng\AppData\Local\Temp\claude\C--modeling-silksong-bot\99d0a17d-64d3-4738-80f4-0ed168134124\scratchpad\upy\.venv`,
   dumps `upy\fsm_*.txt`); the 7 logged ground releases fit a ground-only timer with a threshold in 0.183–0.283 s.
2. Ground dash into an adjacent wall: the Ground Sprint OnEnter Translate pushes the model's box into the wall and the
   sprint runs through it (held-out T1, 6 dashes, 3 u); the sprint FSM ends against the wall in the game.
3. Mantle (Mantle FSM dump in `upy\fsm_Mantle.txt`: Check Forward rays, Cling, Vault +1.6, Land) — not in the Forum
   arena, but in the test rooms; at least predict the AIR MANTLE trigger so the planner avoids it.
4. Glide inflate 11 vs 12 frames (held-out T2) and the one recoil off an object missing from the TERRAIN dump.
5. Reaper dash attack movement (Sprint FSM Reaper Antic / Upper / End) is not modelled; Clawline not started.
6. More fresh held-out data for a second freeze (new seeds from 98800; 98600 / 98700 are spent).

## Chain F0 - Forum round R0: tables on all closed fights, held-out recall, data products (branch worktree-wf_198518ec-9ba-1)

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_198518ec-9ba-1`, branch `worktree-wf_198518ec-9ba-1` (from main
07bda48). Offline only (no game instance touched). Facts: `docs/facts/1.0.30000/forum.md` §12 (Chinese). Large outputs
(not in git): `C:\ssbot\data\m2_forum_r0\` (`build_all\extra` per-fold supports + contacts + walk tables, `cache` per-
fight caches 728 MB, `fresh\` + `cache_fresh\` the 35 fights closed after the build, `recall_*.json`, logs,
`pipeline*.ps1` / `fix_*.ps1` drivers).

### Done (developer round)

- Tables rebuilt from the 107 closed complete gauntlets (frozen list `build_all\fights.json`; 25.4 h fight time; 6.6 h
  build). In-sample validation did not pass (`coverage.json` `validation.ok = false`, built with
  `--allow-failed-validation`): 55 uncovered and 19 unexplained contacts in sample, 56 outside attacks; the margins and
  structural items of the recall carry them.
- `behaviour_build --extra DIR`, `--fights-list`; `ssbot.knowledge.forum_cache` + `tools/forum_extract`;
  `ssbot.knowledge.forum_support` + `support_recall --encounter Forum`; `ssbot.knowledge.forum_products` +
  `tools/forum_products`; `tools/forum_simul` (reproduces design H table 1.2); `planner_bench --encounter Forum`.

### Fixer round (after the review; commits 8d12c86 .. HEAD)

The review refuted the first certification (margins of fold k were residuals against fold k's own occupancy; the
structural items were added while looking at the 107 fights' misses; the idle families' templates, anchored where the
idle began, cover most of the arena, so their 100 % was close to vacuous; with per-fold margins the configuration
missed a Clawmaiden slash on 35 fresh fights). Fixed:

- **3-way split** (`support_recall --split 3way`, the default): fold k's fights against fold 1-k's tables, fold k split
  in two halves, each half certified with margins from the other half's contacts (their held-out residuals are against
  fold 1-k, the tables used). Tables, margins and certified contacts are disjoint. `--split 2way` keeps the leaky one.
- **Idle body tube** (`forum_support.IdleTubeCalibration`, `SubjectRecall.in_idle_tube`): an enemy in its idle family is
  forecast by its damage box as last seen (no box: the type's body hull), moved along its exported velocity and grown by
  g[game-time bin] calibrated on training fights (largest dead-reckoning residual of idle bodies per type and 1/60 s
  bin, monotone; bins by game time because a 0.48 s hitch in 4 frames made the Clapper's per-frame g 7.9 u). The current
  idle instance's templates are not placed; attacks it may start are placed as before; idle families get no margin.
  Production g at 4 bins 1.33-2.52 u; it grows to 3.6-14.9 u at 40 bins (fine for lags, not for a 0.8 s horizon).
- **Unnamed sources**: a `damage_blocked` source naming only a collider child (`Colliders/Collider Fly`) was given by
  the builder to one Minister exporting it, not always the one touching (223640 i2/ep0 f767636: 7 u away, "covered"
  only by its arena-wide Chase template). Every subject of the type is now a candidate (from the oracle event's own
  source, `forum_support.raw_sources`), counted apart.
- **Fresh certification** (`support_recall --fresh`, `behaviour_build --contacts-only --exclude-fights`): the 35 fights
  closed after the build (074533 i2 ep25-41, 074719 i3 ep25-42; 74,120 non-follow-up contacts), configuration frozen at
  da1cd41 before the run, each fold's tables, production margins (largest held-out residual over all 107 fights' contacts)
  and tubes calibrated on all 107 fights. `support_margins.json` now holds that run (`certification: "fresh"`) with the
  development cross-fit in `development`.
- `support_area`: the thrown hazards' self templates are in; absolute **band cover** (the template anchored at the
  centre of the Forum band x 14.01-48.99, y 3-18, with the hero half-extents and the margin) next to the area ratio; the
  idle body tube's area and band share at 4 bins.
- Products: **chains** by the hero's own mechanism (Multihit tick `special_damage` ~20 frames before the Final Hit
  `DamageHeroDirectly` that names the source; no timing-only attachment); **kill_freeze** lengths from the oracle's end
  events, ends past the cached fight read from the recording, censored ones counted; **strikes**: hazards attributed at
  their spawn (the first frame of the unarmed lead-in), body-only strike time for the Tiny's ram (AT_FIRE), fastest per
  type by p5 with the kind.
- Provenance: `git_info` reads HEAD from the `.git` files when the git process fails (the detached build wrote sha
  null); `behaviour_build` exits 4 for a multi-enemy arena without a revision (`--allow-no-sha`); the tables' and
  coverage.json's `code` patched to 7d09798 with a note. `planner_bench --idle-growth` (the idle body tube in the bench).
- Tests: `tests/test_forum_r0.py` 20 (idle tube calibration / query / not placing the idle instance, 3-way margins,
  mechanism chains, uncensored freezes, spawn attribution and body strikes, band cover, contacts-only, git files, the
  bench's tube).

### Key measurements

- **Certification (35 fresh fights, frozen config da1cd41, production margins): 74,120 / 74,120 at L2, L3 and L4 with
  fold-0 tables and again with fold-1 tables.** Not by the forecast itself: same-name 9 and unnamed-source candidates 4
  per lag; no tube needed. The idle body tube (part of the forecast) covered 133-147 per lag. What passed are the
  production margins (CM_SLASH 0.7048 u), not per-fold or per-half ones.
- **Development cross-fit (107 fights, 3-way split, da1cd41): 228,333 / 228,333 at L2, 228,332 at L3 and L4
  (99.9996 %).** The miss: Clawmaiden "Slash 5" at 074719 i3/ep5 f281119 (residual 0.068 u against the other fold's
  Slash 5 template; its half's CM_SLASH margin was 0.0). Not by the forecast: same-name 46-47, unnamed-source 15-18,
  collider tube in an attack 21-23, hazard tube 0-1 per lag. Without margins: 100 / 99.9996 / 99.9991 % (the same slash and a Reed Stab 5 at L4) with the collider tube 48-49 and hazard tube 5-6 per lag doing more: the margins add little, the structure and tubes carry the recall.
- Production margins (38 = 29 attack families + 6 hazards + 3 entries; idle families none): 21 under 0.5 u; 3.0 u (cap)
  for MI_PARRY, AT_FIRE and the pin / spear / bell / bomb; EN_CHARGE 2.96, CM_SPIN 2.76, RE_DEFEND 2.62, CC_JUMP 2.11,
  CH_JUMP 1.61, RE_STAB 1.37. Area ratio over 48 (42 enemy families + 6 hazards): median x1.13, max x7.4 (Reed pin), 12
  above x2 (4 hazards + 8 enemy families; enemy families alone median x1.12, max x4.3). The first report's "max x4.3,
  12 families above x2" left the hazards out and counted RE_IDLE / RE_STAB (10 enemy families were above x2 then).
- Band cover (median bin, no margin -> production margin): idle templates (no longer placed) Tiny 93 %, Clawmaiden 63 %,
  Bellbearer 62 %, Minister 55 % (max bin 96 %); the idle body tube at 4 bins 6-20 %. **Moving attack families are wide
  too**: CM_SPIN 74 -> 99 %, AT_DEFEND 75 -> 79 %, RE_STAB 66 -> 77 %, MI_PARRY 52 -> 76 %, AT_FIRE 30 -> 64 % (max bin
  100 %), bell 34 -> 65 %, RE_DEFEND 26 -> 50 %.
- Products (107 fights): multi-hit chains are at most 2 hits / 2 masks (Minister slash 806 of 831, whip 381 of 401, Reed
  counter 203 of 227; 1,470 ticks, 80 without a final hit); EnemyBattleEndSlow 112-138 frames (p50 114, 1.90 s; max
  2.47 s; 104 measured, 9 of them read past the cache, 4 censored), BigEnemyDeathSlow 9-10 frames, Clapper only; fastest
  strike p5 >= 0.40 s for every type (CC_CAST now 0.400, was 0.067; Tiny ram by body 0.90 s, 4,063 of 7,963 rams reach
  the hero's commit box), minima below 0.35 s only in hazard families (bell 0.0, pin 0.1, CC_CAST 0.117); CC_JUMP_CAST
  p5 1.80 s (was 0.82: the rune slam spawns 65 frames before it arms).
- Unchanged from the developer round: quiet stretches (1,038, 37.6 % >= 1.52 s), Garmond (nearest to him 53 %),
  stance counters (Minister 241 / Reed 175, parry 5), below-flier shares, Clawmaiden distance, bells, boundaries.
- planner_bench with the idle body tube (--idle-growth, same fight / frames): placements per tick p50 28,172 (was 28,506), tick 100 / 323 ms p50 / p99, every candidate still meets the support: the tube fixes the vacuous idle support, not the cost; the placements are the attacks that may start at 0.2 s anchors x 2 mirrors.

### Next

1. R2 (MultiForecast) must keep what the certification used beyond per-state templates + production margins: the idle
   body tube (calibrated to the planner's horizon: 0.8 s = 48 bins, and better than dead reckoning for hopping /
   chasing idles), attacks it may start at velocity-extrapolated anchors, thrown hazards by self template (armed: from
   arming; in the export but not armed: may arm where it is), the family-wide union, entry families' world-fixed union,
   same-name / unnamed-source candidates (the runtime forecasts every enemy anyway), and the collider / hazard tubes.
2. Moving attack families (CM_SPIN, AT_FIRE, AT_DEFEND, RE_STAB, MI_PARRY, RE_DEFEND) have templates covering 50-99 % of
   the band at their median bin: re-anchor them at the current position (or condition them on the path) as the idle
   ones now are, then certify again on fresh fights.
3. Builder attribution: the source path's "Wave N/..." parent and the toucher's position tell same-named enemies and
   collider-only sources apart (today 9-18 contacts per lag need the candidate rule).
4. R1 data: multi-hit chains with LethalBlock off and high HP (whether the tick count depends on health), dash-stab
   reach (the 7.0 u estimate vs the Clawmaiden's median 8.0 u), Envoy ambush (107 instances), HopSlash never seen.
5. Any later change to the forecast structure needs a new fresh set (the next recordings); the 35 fights used here are now seen.

## Chain F - Forum setup, gauntlet tables, data policy (branch worktree-wf_946a7803-63c-2)

Original title: HANDOFF - Task F (Forum, M2 W8) - round 3, fixer (finished normally, 2026-10-03 ~02:20 PDT)

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_946a7803-63c-2`, branch `worktree-wf_946a7803-63c-2`.
Instance 2 (port 47019). Seeds 95100-97999 (used as --seed bases: 95100, 95200, 95300, 95400, 95500).

### Running job (left running on purpose: data collection with the fixed code)

- Run G: `C:\ssbot\data\runs\m2\20261003_014254_Forum_A_data`, instance 2, started 2026-10-03 01:42 by the chain
  `C:\ssbot\sandbox\fo_chain.ps1 -Tag G` (log `C:\ssbot\sandbox\fo_chain_G.log`) from the frozen worktree
  `C:\ssbot\live_fo_9a14574` (code 9a14574 = all fixes below): `combat_run run --instances 2 --encounter Forum_A
  --mode data --policy data --hours 9 --episodes 100000 --seed 95500 --threads 4 --timebox 0 (Forum default now 1500)
  --rotate 5`. Ends by itself about 10:45 on 10-03; about 4 episodes per hour; a recording closes every 5 episodes.
- Stop: `cd C:\ssbot\live_fo_9a14574\brain; ..\scripts\uv.cmd run python -m ssbot.tools.combat_run stop
  C:\ssbot\data\runs\m2\20261003_014254_Forum_A_data` (ends after the current episode, <= 17 min). STOP_AGENTS also
  stops it.
- Run F (`20261002_231917`, e589c0b) was stopped gracefully at 01:42 after 10 episodes (all CLEAR, both recordings
  closed). Live worktrees `C:\ssbot\live_fo_3fa0375`, `live_fo_7eb12de`, `live_fo_c86979f`, `live_fo_e589c0b` are no
  longer used (remove with `git worktree remove`); `live_fo_9a14574` runs run G.

### Runs (all fo_A, data policy, instance 2)

| run | code | episodes | note |
|---|---|---|---|
| 20261002_221727_Forum_A_data | 3fa0375 | 2 | false CLEAR before the finale - not used |
| 20261002_223640_Forum_A_data | 7eb12de | 2 | complete gauntlets |
| 20261002_230325_Forum_A_data | c86979f | 1 | complete |
| 20261002_231917_Forum_A_data | e589c0b | 10 | complete, pocket mode (85 % of the frames on the wall with only Clappers left) |
| 20261003_014254_Forum_A_data | 9a14574 | running | live check of the fixes: ep0 CLEAR, f_end = freeze + 270, waves in order (2 -> 3: 1.5 s) |

### Done this round (fixer; commits 379e33e .. e9eddb4)

- episode (6a38ba3): eval-mode lethal hit with or after the kill -> WOULD_DIE (checked before the kill check, in the
  post-clear window, and after the loop); `Encounter.post_clear_s` (Forum 4.5 s: EnemyBattleEndSlow + 1 s +
  battleEndPause 2 s until hang04Battle, about 245 frames); the policy keeps acting in a gauntlet's window;
  `AttemptRecord.lethal_after_clear`; Forum timebox 1500 s. Tests: tests/test_episode_post_clear.py (5, fail on the
  old code).
- gauntlet (379e33e): WaveSim runs BattleScene's 1 s enemy-count check after each activation (index 3 starts 1.5 s
  after index 2; starts in time order; duplicate StartWave ignored); kill counting keeps repeat deaths of pooled Tiny
  (hp_before > 0, same iid again after 60 frames). Replay on all 13 complete gauntlets: end = freeze frame in all;
  Clawmaiden activations 0.02-0.47 s after the sim's wave 3 / 5 / 10 starts.
- data policy (ccb85d1): pocket share set by frames (POCKET_CLING_SHARE 0.85 = what run F did; behaviour unchanged).
- gauntlet tables (9a14574): folds per fight; collider-child contacts look back LAG_F frames, else nearest live subject
  of a type exporting that name (counted unexplained), unattributed contacts listed and failing; every table has
  `validation.support_conservative` + `support_note` and distinct uncovered contacts; coverage.json `validation` per
  type (in sample, held out); BossModel warns on a non-conservative table (`support_ok`).
- Tables rebuilt from 13 complete gauntlets (e9eddb4), forum.md corrected and extended (§3 post-clear window, §8.1
  cling-height mechanism unverified + HeroBoxWallScramble, §9.2 kills / wave timing / episode length, §10.1 apex
  spread, §10.2 Slam Range layer matrix, §10.3 regenerated, §10.4 rules, §11 regenerated from coverage.json).

### Key measurements

- Slam Range (layer 13 Hero Detector) collides only with layer 9 Player; the only layer-9 collider is the hero's root
  physics box (Hero_Hornet). Helpers (14/15/17/22/24/13), Cogfly (14/15/17/18/19), Clappers (11) cannot trip it.
- Pocket (13 fights, 413 jumps, 2343 pocket frames): only flush-wall takeoffs (x 15.36-15.95, facing right, hero to its
  right) enter the pocket (9 of 12); jumps with the hero on the wall (105): median 4.3 u, nearest 0.87 u (takeoff 17.77
  facing left); the only Clapper contact in the pocket was damage_blocked. Rule added: in the pocket, any Clapper
  facing left at pos <= ~18 is a threat.
- Tables: 28,029 contacts, 19 distinct failures (5 are kill-frame body contacts), 0 unattributed (21 recovered by the
  lookback); held out beyond R_FAIL 0.3-5.2 % per type (Clawmaiden 5.2, Reed 3.0, Tiny 1.6) -> no type conservative.
- Hours to 200 (fight time ~ wall time per instance): CM_TELE 4.8, AT_LEAVE 2.7, CH_JUMP 2.4, then <= 0.5; Envoy and
  entries far off (Envoy ambush 44 h).
- Kills (13 gauntlets): 541 deaths = 364 wave + 177 Tiny; Garmond 201, Hornet nail 270 + spear 45, Cogfly 17.

### Next

1. When run G has 2-3 more closed recordings: rebuild (`cd brain; $env:NUMBA_NUM_THREADS=4;` below-normal priority;
   `..\scripts\uv.cmd run python -m ssbot.tools.behaviour_build C:\ssbot\data\runs\m2\20261002_223640_Forum_A_data
   C:\ssbot\data\runs\m2\20261002_230325_Forum_A_data C:\ssbot\data\runs\m2\20261002_231917_Forum_A_data
   C:\ssbot\data\runs\m2\20261003_014254_Forum_A_data --encounter Forum --allow-failed-validation`, ~110 s per
   episode) and regenerate §11 (script logic: numbers from coverage.json only); watch the held-out shares fall.
2. Kill-frame contacts: the scanner ends an instance on the kill before the same-frame contact; give the dying body a
   short "death" window (and the finale Clapper's 'Start Battle?' after ZERO HP) so the planner sees it.
3. Envoy targeted collection; reliable wall climb for the pocket (145 of 5621 wall frames reached the top).
4. Oracle allies / room.battles exports still not deployed; Ascendant's Grip pickup location unknown.

## Chain H - pause / quit safety (branch worktree-wf_c0d56d51-4cb-4)

Original title: HANDOFF: chain H (pause / quit harness and safety follow-ups, M2 W5)

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_c0d56d51-4cb-4`, branch `worktree-wf_c0d56d51-4cb-4`.
Instance 4 (port 47021), seeds 100000-104999, savestate prefix pq_ (none made). Facts: docs/facts/1.0.30000/pause_quit.md.

### Done
- Injector (brain/ssbot/train/hit_injection.py): faults hit / trigger (Supervisor.inject "QF") / menu (both), hard
  moments taken on their first frame (bounce, Silkspear cast, kill) or before a committed kill (planner-scored
  Silkspear at press + 19 + offset, nail press); hits wait out the hero's invulnerability; "keys" trigger = a key
  pressed in flight; SSBOT_INJECT_KINDS restricts kinds. pause_stress measures fault frame, moments, latency from the
  open-gate stretch, keys on menu-visible frames, --natural baseline.
- Menu key guard (brain/ssbot/safety/key_guard.py + PauseCues.keys_clear + SupervisedControl.step(inflight=)): the
  loop's first Pause waits until no game key can be latched / replayed on its landing frame.
- Oracle ACTION EXCLUSIVE flag (10d3948): built with -p:Deploy=false, NOT deployed. Brain sends it already (5th
  element, ignored by the deployed oracle).
- Fixes: supervisor Q1 with a certified-empty support (10bfb66, behaviour change, see facts §5); episode kill path
  HARNESS_FAIL (45c8ebb); combat_run worker start in a new-game session (67cbaca).
- Measured chunk 20261002_232051 (30d542b, 100 trials): 52.5 % within +-3 frames of a hard moment (43.4 % without
  menu), 99/99 paused + main menu, latency max 3 frames, 0 leaked keys / unpauses / wrong submits.
- Instance 4's sandbox had no slot 1: copied user1.dat / user1_1.0.30000.dat / shared.dat from
  C:\ssbot\sandbox\saves\0\default (identical in instances 0-3). Void runs: 20261002_224118, 20261002_224732
  (0 episodes, load_slot on the empty slot).

- Check chunk 20261003_001326 (e34da27 = all fixes, 93 trials): 49.5 % (38.7 % without menu), 93/93 paused +
  main menu, latency max 3, 0 leaked keys / unpauses / wrong submits / refused hits / HARNESS_FAIL. After trial 93
  instance 4's game process vanished (log cut off mid main-menu load, no crash dump, not my doing); relaunched.

### Running
- Pause stress campaign, detached (Win32_Process Create, survives this session): worktree
  `C:\ssbot\live_pq_e34da27` (e34da27, numba prewarmed), instance 4, seeds 100600-104999 (4400 trials, about
  37 h at 30.4 s per trial), run dir `C:\ssbot\data\runs\m2\20261003_010522_BellBeast_eval_planner_oracle_inject`,
  launcher log `C:\ssbot\sandbox\pq_campaign.log`, worker log `<run dir>\worker_i4.log`.
  Stop (graceful, after the current trial): from `C:\ssbot\live_pq_e34da27\brain`:
  `..\scripts\uv.cmd run python -m ssbot.tools.combat_run stop C:\ssbot\data\runs\m2\20261003_010522_BellBeast_eval_planner_oracle_inject`
  (or C:\ssbot\sandbox\STOP_AGENTS). Instance 4 holds SsOracle.dll while it runs: stop it before deploying.
  Summarise: `..\scripts\uv.cmd run python -m ssbot.tools.pause_stress <run dir> --quiet --json <run dir>\pause_stress.json`
  (reads every recording: run it at below-normal priority, about 1 s per trial).

### Needs deploy
- 10d3948 oracle ACTION EXCLUSIVE flag (HoldFilter.Exclusive, brain-lost Pause tap exclusive, HELLO action_flags,
  input.stats hold.released_early). Brain already sends the flag. After deploying, the Python key guard can model
  EXCLUSIVE (keys_clear would then always pass) to save its 0-2 frame wait, if the lead wants.

### Next
- To reach 10^4 trials: another seed range (this chain's ends at 104999) or more instances.
- G1 also asks for greyed-Quit, focus-loss and Steam-overlay injections (not done here).
- Decide whether the supervisor's h for the tier (not only Q1) should also use the worst known event when the
  support is certified empty (at 3 HP with the boss underground the tier is GREEN today).
- Lead: merge facts/pause_quit.md into probes.md as needed; the supervisor Q1 change (10bfb66) is a behaviour change.

## Chain V - Bell Beast vision-equivalent view (branch worktree-wf_946a7803-63c-1)

Original title: HANDOFF: task V (Bell Beast in the vision-equivalent view), fixer round

Worktree C:\modeling\silksong_bot\.claude\worktrees\wf_946a7803-63c-1, branch worktree-wf_946a7803-63c-1.
Findings: docs/facts/1.0.30000/m2_vision_view.md, "第三轮" (round 3 = this fixer round) at the end; it also marks
round 2's live numbers (sections 10-12) as measured with an oracle supervisor / pause machine.
Live runs go from the detached worktree C:\ssbot\live_vv (checked out at the commit under test, numba prewarmed
with planner_bench on a recording). Instances 0 and 1 (ports 47017 / 47018) are left running idle; the lead runs
launcher --restore.

### Done (fixer round, commits d9faaff .. 4a90331; later commits are docs)

- d9faaff: stage C supervisor and pause machine read only the delayed view (supervisor.input_from_world,
  pause_quit.vision_cues_from_state: dimmer, stopped world, menu reader; no paused flag, no pause gate); no hero hits
  newer than the WorldState in the planner's start state; unpredicted hits judged only at lags 3 / 4 / 2, else
  unpredicted_unknown (also counted for Q4).
- 8809999: the hero's hits on drop bells are modelled in the vision view: pogo_targets.tink (the FSM's rule; TINK LEFT
  is -10 for |vx| <= 5, simulate had -5 in both views), bell_track keeps tink branches instead of withdrawing a
  touched bell, VE bell targets on (drop bells redirect on their branch, pogo only while falling), a bell with open
  branches makes attacking plans unsafe; train/bell_hit_monitor (live, stats()["bell_hits"]) and
  tools/bell_hit_audit (offline property test, both views).
- 3f6de98: cues only inside the image; a cue that comes into the image late is bounded by the camera history; cue
  onsets drawn in their evidence bracket ((0.1, 0.3] s, low/tall (0.3, 0.6] s), TELL_DELAY / TELL_SLACK_S re-centred.
- 65fab69: SimpleNoise per-track persistent bias (placeholder 0, SSBOT_NOISE_BIAS for audits), ghosts keep their last
  detection's offset; boss_path_audit --check-margins (held-out exceedance of the pogo-gate margins).
- 3dd640f: real-quit menus keep the last WorldState (outcome reason only).
- 4a90331: tick cost back to the ec62558 level (the new exact paths had made bursts 3-4 ms slower: 60-180 late ticks
  a fight and attack-bell hits in 12 of 16 live episodes of 20261003_043306 / 050343, both stopped).

### Measured (details in the facts file)

- Held-out recall (i2_002 / i3_002, held-out tables, lags 2-4): 23,896 / 23,896 for ve_dust noise seeds 7, 11, 23
  (margin 0), seed 23 at the live margin 0.335 u, and oracle; again after 4a90331 (seed 7, oracle).
- Property test (bell_hit_audit, 171806, 24 fights, at 8809999): 0 violations in 32 + 32 tinks; the old withdrawal
  gives 9 / 9 violations.
- Pogo-gate margins on held-out fights (20261003_014409, 12 fights): 8 / 31,505 residuals beyond (max 0.09 u);
  with a 0.05 u persistent bias 67 / 31,543 (max 0.066 u).
- Live degraded_dust on 4a90331 (20261003_053033, instances 0 / 1, seeds 91200+): 150 valid, 141 CLEAR (94.0 %,
  95 % CI 88.9-97.2), 9 QUIT (attack bells 7, charge body 2, rage pattern 0), 0 WOULD_DIE, 0 HARNESS_FAIL,
  0 unpredicted; bell-hit monitor 235 tinks, 0 violations; late ticks p50 7 / p90 17 a fight, tick p99 median
  19.1 ms. Stopped at 150 by the lead's STOP_AGENTS (oracle deploy window, 07:33).
- Stopped runs (not evidence for the final code): 20261003_043306 (65fab69, 10 eps) and 20261003_050343
  (3dd640f, 6 eps), both with the tick-cost regression fixed in 4a90331.

### Stopped here (STOP_AGENTS, 2026-10-03 07:33): not done yet

- Oracle-view regression on the final code (both views share the left-tink fix, the exact-path caches and the
  unpredicted accounting): about 60 episodes, e.g. from C:\ssbot\live_vv\brain (already at 4a90331, numba warm):
  `..\scripts\uv.cmd run python -m ssbot.tools.combat_run run --instances 0,1 --encounter BellBeast --mode eval
  --policy planner --view oracle --threads 4 --real-quit 0.2 --seed 92000 --episodes 32`.
- Offline property test on the final code (tools/bell_hit_audit, both views; last run at 8809999) and rec_stats
  (pogo hits per charge) on 20261003_053033.
- Nothing of this task is running.

### Next

- See the facts file, round 3 section 9 (remaining issues): off-screen bell columns and the union shortcut, the rage
  prune's hit-count assumption (M3), the persistent-bias size (M3), bursts / rage pattern / Dig In pogos.
- To stop a running job: `..\scripts\uv.cmd run python -m ssbot.tools.combat_run stop <run dir>` from
  C:\ssbot\live_vv\brain (or this worktree's brain).

## Chain Q - low-HP heal-or-quit rule, Q1 / Q1a (branch worktree-wf_9edc2274-509-2)

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_9edc2274-509-2`, branch `worktree-wf_9edc2274-509-2`, from main
5a83283. Instance 4 (port 47021), seeds 105000-109999, savestate prefix pq_ (none made). Facts:
docs/facts/1.0.30000/pause_quit.md sections 7 (this rule) and 8 (EXCLUSIVE deploy checklist). This answers the
integration section's Next item 4.

### Done

- Supervisor (`safety/supervisor.py`): h is hits_to_death against the support, and against the encounter's worst known
  event when the support is certified empty (`SupervisorDecision.h_basis`); every rule reads it (tier, Q1, Q1a, Q3, Q5,
  Q6, the Bind commit test's worth clause). Replaces 10bfb66's Q1-only floor: at 3 HP with the boss underground the tier
  is YELLOW with h 2 (was GREEN with h UNBOUNDED, and the commit test refused the Bind as "not worth it"). Q1 (h <= 1)
  quits, never Binds, and records its cause (`q1_cause`: a hit within 1.1 s = the post-hit window, else the first
  pausable frame). Q1a: `Restrictions.heal_first` = h >= 2 and HP < max, in any tier.
- Tactics (`combat/tactics/modes.py`): HEAL with heal_first at any HP < max (4 / 5 too), never at h <= 1; HEAL_SPOT
  walks to a verified floor spot of the playbook (`bind.safe_spots`, `playbook.SafeSpot.usable`, forecast agreeing)
  when only the place fails; else fight on. Bell Beast lists none (playbook comment: the coverage map's only gaps are
  wall-cling points at the gates).
- Post-hit pause timing (`safety/pause_quit.py`, `train/supervision.py`): `PauseCues.gate_open_at` = the predicted
  first pausable frame; no press before it, and from it the press goes even with the gate still seen shut. Measured:
  G (first STATE with pause.blk 0) 0.213-0.267 s after 2138 hits; **the first frame a press pauses is G + 1**
  (the time scale comes back after InputHandler's Update; a press on G is dropped and costs a 6-frame cadence).
  Oracle: the freeze ramp's last shut frame (ts >= 0.999) -> pause on G + 1 (about 60 % of hits), else the observed
  gate's G + 2 as before. Vision (delayed view only): the hit's capture time + 0.285 s (0.57 s through a Bind).
- Harness: `SSBOT_INJECT_LEAVE_HP` / `SSBOT_INJECT_MIN_SILK` (injector "anytime" hits leaving h 1 or 2), `combat_run
  --start-silk LO HI --silk-reserve`; tools `lowhp_check` (live check summary) and `lowhp_replay` (recorded decisions).
- Commits: 5126afd (rule, h, gate_open_at, tactics, tests), 72baaf3 (harness), 3bc9da8 (hit through a Bind),
  8beb806 (G + 1 fix), b957be6 / a2d0ec9 (lowhp_replay), 05382a7 (lowhp_check), d0c2327 / 3afa1e1 (Q1 cause), docs.
- Tests: tests/test_post_hit_window.py (stand-in game with the four measured gate shapes and G + 1; oracle, vision
  k 2-4 x G 13-16, no hit, SupervisedControl wiring, hit through a Bind), Q1 / Q1a / h-basis tests in
  test_supervisor.py, tactics branches in test_planner.py (test_q1a_heal_first_branches), injector option in
  test_pause_stress.py.

### Measured

- Live oracle 20261003_112406 (8beb806, 30 trials, CPU ~75 %): h 1 16 / 16 pause on G + 1 (+16 frames, 0.264-0.268 s
  after the hit, 0.925 s of i-frames left), 0 Binds; h 2 (3 HP) 11 / 14 Binds, 11 / 11 completed, 0 hit, all 11 CLEAR,
  3 Q6 quits. The first version (72baaf3, run 20261003_111244, stopped after 12) timed the press for G: dropped,
  pauses at +20 / +21 (chain H's observed gate: +17).
- Live degraded_dust 20261003_114708 (8beb806, 30 trials): h 1 22 / 22 pending 2-4 frames after the hit (the view's
  delay), paused at +17 (21) / +18 (1) = G + 2 / G + 3, all inside the i-frames (0.89-0.91 s left), 0 Binds; h 2 8:
  5 Binds, 5 / 5 completed, 0 hit, 4 CLEAR, 4 Q6 (3 before any Bind). One h-1 Q1 was labelled "no hit" (its HIT_TAKEN on
  a skipped frame; timing still right): fixed in d0c2327 (a HUD drop counts as a hit) and 3afa1e1 (the cause latched
  while the pause is pending or held).
- Both views together (72 trials): h 1 46 / 46 paused inside the window, 0 Binds; h 2 20 Binds, 20 completed, 0 hit.
- Full suite (code of 8beb806 + tools): 903 passed, 1 failed (the known support-query timing test under load: p99
  2.76 / 4.39 ms vs 3 ms), 1 skipped, 1 xfailed; after d0c2327 / 3afa1e1 (supervisor only) the related tests 86 passed.
- Replay (61 runs, 324 episodes: 311 Q6 quits, 13 heals; 0 Q1 quits and 0 Binds at h <= 1 in the recordings):
  Binds that become quits 0; quits that become Binds 1 (20261002_232157 i1 ep49, degraded_dust: Bind at +152 underground
  with h 2 by the worst known event, where main's rule waited to +214 and the live run quit at +221); 14 new Binds
  checked: support T_min >= 1.7 s, recorded colliders >= 1.07 u away, 0 would be hit (2 censored by the live pause).
  Only 14 of 198 replayable episodes ever had 9 silk after the hit: the Silkspear at full HP spends it, so Q1a binds
  rarely unless `bind.reserve_at_full_hp` is on (A/B needed).
  Corrections from the review (pause_quit.md 7.3 / 7.4): "0 Q1 quits" held only for those 35 plain eval runs (chain H's
  `_inject` runs hold about 580 Q1 quits, replayed in the fixer round); the 2 censored new Binds are unverified, not
  clear (152649 i2 ep3: 5 / 93 frames, and the live run quit 3 frames into the same Bind with a threat 0.93 u away);
  the 113 quit->fight were not attributed one by one (only 44 come from code before d73fe65); every injected hit in
  the live checks had the same freeze shape (G = +15 after a 0.999 ramp frame, the oracle's best case).

### Fixer round (after the review, 2026-10-03 afternoon)

Code: f9dcbba (supervisor / tactics), 4eb57db (tools), 5026372 (combat_run --start-hp). Facts: pause_quit.md 7.7.
- **Q6 at h = 2 removed** (the person's rule, main 1c0a082, DESIGN §3.7.4 Q6 "待实现"): `SupervisorConfig.q6_max_h` = 1
  (2 = the rule before, for an A/B). At h = 2 the bot fights on with the least risky plan, gathering silk: the hit
  weight x `bind.gather_hit_x` (Bell Beast playbook 1.5, a first value, not tuned) while h >= 2, below max HP, silk < 9.
  Q3 still quits at h = 2; the second hit is Q1's quit in the post-hit window. The lead can mark DESIGN Q6 implemented.
- **The tactics read this tick's h** (`SupervisedControl.h_now` / `Supervisor.peek_h`), not the decision a tick old:
  on the tick a hit takes h from 2 to 1 the tactics no longer want a Bind (test_the_tactics_read_this_ticks_h...).
- **A health drop is a hit only with the hit's knockback** (`SupervisorInput.hurt`: cState recoilFrozen / recoiling,
  vision hero mode "hurt"; 28 / 28 sampled hit frames show it on the hit's own frame). Frost / DamageTag drops
  (DoSpecialDamage's take-health path: no freeze, no i-frames) are "no hit": the vision view presses at once instead
  of holding 0.285 s while vulnerable (test_vision_hud_drop_without_knockback_presses_at_once).
- Tools: `lowhp_replay` new-Bind verdict clear / hit / unverified (censored), live Q1 on the hit frame replayed,
  `--q6-max-h`; `lowhp_check` freeze shape (ramp999) per hit, silk gathering, the second (natural) hit, `--q1` scan of
  any run by hit source and shape; `combat_run --start-hp LO HI`.
- Tests: full suite on 5026372 913 passed, 1 failed (the known support-query timing test, p99 4.95 ms vs 3 ms under
  load; budget not loosened), 1 skipped, 1 xfailed (C:\ssbot\sandbox\pq_fullsuite2.txt).
- Replay on 4eb57db (78 run dirs, 649 episodes, pq_lowhp_replay2*.json): chain H's inject runs 303 live Q1 quits
  (010522 sampled 80) all stay quits at the hit tick, Q1 only, 0 Binds; plain eval runs: all 201 live Q6 quits now
  fight on up to the live pause (by design; the 71 "quit->quit" of the first replay are among them), 13 bind->bind,
  1 quit->bind; new Binds 14: 12 clear, 2 unverified, 0 hit (open loop).
- Live oracle 20261003_132436 (4eb57db, injected hits leaving 1 or 3 HP, no start silk, no reserve; the replay ran alongside, CPU not sampled): h 1 10 / 10 paused at G + 1 inside the i-frames, 0 Binds; h 2 20 / 20 gathered 9 silk
  (0.6-33 s after the hit), 20 Binds, 20 completed, 0 hit, 20 / 20 CLEAR, 0 quits (first round, with Q6: 11 / 14 Binds,
  3 Q6 quits).
- Live degraded_dust 20261003_135244 (4eb57db, same setup, CPU ~49 %): h 1 5 / 5 paused at G + 2 (0.282-0.284 s)
  inside the i-frames (vision timing unchanged by the knockback rule), 0 Binds; h 2 25: all gathered 9 silk (6.5-47 s),
  25 Binds, 25 completed, 0 hit, 23 CLEAR, **2 STUCK** (240 s timebox), 0 quits. The STUCKs (new, not fixed): after a
  Bind to 5 HP a second hit left 3 HP with the boss at 15 / 20 HP (the view's count); for the last 25 s the tier was
  YELLOW, h 2, silk 0 / 4, no plan with an attack. Most likely YELLOW's "no DAMAGING when the next hit may kill" (I3:
  the 1.35 s boss-death slow motion only at full HP and h >= 3) with the vision bound hp_est - 3 sigma <= 15
  (VISION_HERO_HIT, the Silkspear) stopped every attack, so no silk, no Bind: a deadlock that Q6 at h 2 used to cut
  short with a quit. Options for the lead / the person (pause_quit.md 7.7): the next hit's bound from the hits allowed
  now (below full HP no silk skill: nail 5; check crits first), or quit at h 2 when silk < 9 and I3 forbids damage.
- Live natural hits (5026372, `--start-hp 3 3 --start-silk 0 0`, no injection; stopped early): oracle 20261003_144536
  18 / 18 healed first (Bind 18-29 s after the wake) and CLEAR, FORCED_RISK in 18 episodes (2591 ticks, each a Q6
  quit under the old rule), 0 quits; degraded_dust 20261003_150835 12 / 12 healed (20-54 s) and CLEAR, 0 quits. The
  boss barely hit the hero, so **natural-hit Q1 timing still has no live sample**; every one of the 62 hits measured
  today on instance 4 (60 injected, 2 natural) had G = +15 after a 0.999 ramp frame. The restarted campaign (h 2 no
  longer quits, so a second natural hit is a Q1) collects them: summarise with `lowhp_check --q1 <run dir>`.
- Campaign 20261003_122030 (3afa1e1) stopped gracefully at 13:22 after 123 trials (seeds 105330-105452). With 120827 it
  had 85 Q1 pauses (pq_q1scan_campaign.json): 82 injected hits with the ramp frame, all at G + 1; 3 injected hits in the
  boss-death slow motion (G +82 / +83), paused G + 3..5, inside the i-frames; no natural-hit Q1.
- Chain H's restart 20261003_074533 (`_inject`, pq_campaign2.log; omitted in the first report): 4 Q1 real quits, then
  ep 4 / ep 5 HARNESS_FAIL ("state condition not met within 2.0s") and the worker died on a `guards.set` RPC timeout
  (instance 4 unresponsive), 3 minutes after the start.

### Running

- (2026-10-04) Stopped at the 00:25 deploy window after 1014 trials (seeds 105453-106466); restarted on the EXCLUSIVE
  DLL by chain X (below). The text that follows is the state before that.
- 10^4 pause stress campaign on the final code: worktree `C:\ssbot\live_pq_final` (5026372, numba prewarmed),
  instance 4, seeds 105453-109799 (4347 trials, about 36 h; 109800-109919 were the fixer round's checks), run dir
  `C:\ssbot\data\runs\m2\20261003_153044_BellBeast_eval_planner_oracle_inject`, launcher log
  `C:\ssbot\sandbox\pq_campaign_q3.log`, started detached (Win32_Process Create) with
  `C:\ssbot\sandbox\pq_campaign_start.cmd C:\ssbot\live_pq_final 105453 4347 C:\ssbot\sandbox\pq_campaign_q3.log`.
  Stop (graceful, after the current trial): from `C:\ssbot\live_pq_final\brain`:
  `..\scripts\uv.cmd run python -m ssbot.tools.combat_run stop C:\ssbot\data\runs\m2\20261003_153044_BellBeast_eval_planner_oracle_inject`
  (or C:\ssbot\sandbox\STOP_AGENTS). It holds SsOracle.dll: stop it before the EXCLUSIVE deploy. Summarise with
  `pause_stress <run dir> --quiet --json <run dir>\pause_stress.json` and `lowhp_check --q1 <run dir>` (natural-hit
  Q1s by freeze shape), below-normal priority. Behaviour differs from the earlier chunks: h 2 no longer quits (Q6).
- Stopped: 20261003_122030 (3afa1e1, see above); chain H's 20261003_010522 died at 07:13 after 722 trials (Next 2);
  a 23-trial start on d0c2327 (20261003_120827, seeds 105300-105322) was stopped to pick up 3afa1e1.

### Needs deploy

- Nothing new from this chain. The EXCLUSIVE oracle flag already in main: checklist in pause_quit.md section 8 (stop
  this chain's campaign on instance 4 first; it holds SsOracle.dll).

### Next

1. The h 2 STUCK deadlock (Fixer round, dust 2 / 25): decide between a finer "next hit may kill" bound below full HP
   and a quit when silk < 9 and I3 forbids damage; then a dust A/B of the h 2 arm (`SSBOT_INJECT_LEAVE_HP=3`).
2. Tune `bind.gather_hit_x` (1.5, untuned) and A/B `bind.reserve_at_full_hp` now that h 2 fights on: time to 9 silk
   after the hit (oracle 0.6-33 s, dust 6.5-47 s today), Binds, time to kill, STUCKs.
3. Chain H's campaign died at 07:13 (722 episodes, 20261003_010522): `load_slot` after a real quit timed out waiting
   for gameplay (TimeoutError in the worker); its 07:45 restart (074533) died on a `guards.set` timeout after 2
   HARNESS_FAILs. The worker has no retry there. Watch the restarted campaign for both (its log and worker_i4.log).
4. Natural-hit Q1 timing: none live yet (above); read it from the campaign with `lowhp_check --q1`. Expect G + 1 after a
   0.999 ramp frame, G + 2 without; a G + 3 or later outside the boss-death slow motion is a finding.
5. Safe spots for later encounters (Forum left wall top, Lace 2 arena): need a cling / double-jump primitive in the
   planner before `SafeSpot.kind == "wall"` can be used; verify each with coverage_map first.
6. Live workdirs: `C:\ssbot\live_pq_final` (5026372, runs the campaign). No longer used, removable with
   `git worktree remove --force`: `C:\ssbot\live_pq_72baaf3`, `C:\ssbot\live_pq_3bc9da8` (at 3afa1e1),
   `C:\ssbot\live_pq_4eb57db` (the fixer round's injected checks).
7. Merge note: main's 1c0a082 marks DESIGN §3.7.4 Q6's revision "待实现"; it is implemented here (q6_max_h 1).
   The Bell Beast gate on main (e3ceda4: degraded_dust 4a90331, 94.4 % CLEAR) ran with Q6 at h 2; after merging, the
   gate's QUIT / STUCK mix changes (h 2 fights on), so re-run it on the merged code before quoting it.


## Chain K - key economy: few presses, few key plan changes (branch worktree-wf_48b03215-cdd-1)

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_48b03215-cdd-1`, from main 97b40f6. The person asked (2026-10-03
night) whether "few presses, few changes to the key plan" is in training; M2 plan "key economy" (third after safety and
time). Facts: `docs/facts/1.0.30000/key_economy.md` (Chinese, all numbers); M2.md key economy section has the status.

### Done (committed)

- `train/keyplan.py` KeyPlanLog (moved out of `combat/` on 2026-10-04: it imports `ssbot.ipc.framing`, and `combat` is a
  final-run package the import firewall keeps away from the oracle; `test_import_firewall` failed on 6d88f74): per key, every note (press) from the tick that first decided it, every change /
  cancellation (late ticks too), executed, open releases, frame-level flip-flops, and the presses the game latched
  (STATE act.mask every frame, caught-up STATEs included); `summarize`, `match_actual`, `final_press`.
- `train/planner_policy.py`: `keys_i<N>.jsonl` in the run dir, one line per episode (13-101 KB; off arm 29-57, p50
  40; the 101 KB line is a 240 s STUCK), always on; `stats()["keys"]` summary in the attempts. Supervisor keys are
  notes flagged sup. Decision log rows carry `keys` when the terms are on: the off choice, swap flag, J_off, kp / kc,
  risk / risk_off.
- `combat/planner.py`: playbook weights `key_press` / `key_change` lower J (`_key_terms`, numba `_key_costs`, which
  since 2026-10-04 matches presses run to run like the key log: moved / dropped / added 1, release moved 0.5; the first
  kernel charged a 1-frame move 3 and a drop 1.5), but only within the safety class of the choice made without them
  (`_key_economy`: same Hz, Hz_soft, U, S, jump / macro commitments, comfort, V, P, first contact; tail check required
  when the original passed it) AND within the bound added 2026-10-04: unlowered J within `key_tie` (KEY_TIE 0.05),
  end risk map value not higher, a new jump hold not longer, no macro unless the choice is one (`key_tie` < 0: the old
  class-only rule, analysis only). `PlanResult.cls`, `cls_off`, `idx_off`, `name_off`, `J_off`, `risk`, `risk_off`,
  `key_press`, `key_change`, `key_on`. `combat_run --key-cost PRESS CHANGE [TIE]` overrides the playbook.
- NOT adopted (reverted 2026-10-04 after review): `BellBeast.yaml` has `key_press: 0`, `key_change: 0`. The first A/B's
  w1 had hits 4 vs 5 but FORCED_RISK ticks per fight second +5.3 % (MW p 0.031, seed-paired p 0.057) and non-green
  tier time +21.5 % (MW p 0.030); w2 2.4x / 2.8x. The per-tick class invariance holds by construction and says
  nothing about closed-loop safety (J holds the risk / stance terms; jump holds commit later ticks).
- Tools: `tools/key_economy.py` (safety leading indicators per arm: FORCED_RISK and non-green tier ticks per fight
  second, hit fights; `compare` gives MW / seed-paired sign-flip / Fisher p and a `gate`: ratio <= 1.02 and p >= 0.2
  for both indicators, hit fights p >= 0.2, WOULD_DIE not more, time to kill CI upper < +2 s; presses / s per key, holds, plan change rate per key, decision lead, changes by frames
  before the press, flips; `--arm NAME RUN...` groups compared; the person's fight 64275-68397, menu actions excluded:
  the person's 11 "enter" are the jump key 1 frame early), `fight_stats --keys` (same, per view),
  `tools/key_cost_check.py` (replay property check; `--tie`; bound violations, J given up, risk diff),
  `tools/key_track.py` (renderer prototype).
- Tests: `tests/test_key_economy.py` (log semantics, cost kernel, synthetic and recording property tests, renderer);
  `test_planner_policy` checks the keys file of the pause test. Full suite 2026-10-04 (below normal,
  NUMBA_NUM_THREADS 4, playbook back at 0 / 0): 927 passed, 1 failed, 1 skipped, 1 xfailed. The failure is
  test_hitbox_tables' support-query budget (p99 3.44 ms > 3 ms under below-normal priority and load; fails on main
  7733c98 too). test_import_firewall passes again (keyplan moved to train/).

### Measured

- Property: 21,001 replayed ticks (4 recordings of 20261003_175813 / 175958, weights up to 0.3 / 0.6): 0 class or tail
  mismatches; the choice changed on 12-20 % of ticks; tick time unchanged. By construction; not a safety result.
- Bound (2026-10-04, 4,001-tick replays of off-arm recordings 213031 i2_000 / 223152 i3_000, new kernel): class-only
  rule at w1 swapped 293 / 282 ticks, giving up J p50 0.058 / 0.045, max 0.36, a deeper end risk on 17 % / 10 % of
  swaps, 2 longer jump commitments; at w2 531 swaps, J p50 0.12, max 0.97. With key_tie 0.05: 145-147 swaps at w1 and
  w2 alike, J given up <= 0.05, 0 risk / jump violations. Tick p50 +0.05-0.13 ms.
- Old baseline (175813 + 175958, 241 fights, recordings): 4.67 presses / s, the person 2.37 / s; left + right 3.4 / s
  vs 1.05, ~40 % of the bot's direction presses are 2-3 frame taps.
- A/B (class-only rule; instances 2 / 3, oracle, seed 112000, 110 fights an arm, both arms on both instances): off
  4.39 presses / s, plan change rate 43.5 %, 5.98 changes / s, lead p50 2 frames, FORCED_RISK 1.47 / s, non-green
  1.80 / s; w1 (0.05, 0.1): 3.46 / s, 39.4 %, 2.90 / s, FORCED_RISK 1.55 / s, non-green 2.19 / s; hits 5 vs 4,
  WOULD_DIE 0 / 0, time to kill 60.05 vs 59.91 s; w1's 2 non-CLEARs: a Q1 QUIT after 2 hits and the known STUCK
  (below). w2 (0.15, 0.3; 85 fights, stopped by DEMO_SOON): 2.83 / s, FORCED_RISK 3.48 / s, non-green 5.04 / s, hits in
  8 fights (p = 0.045). key_economy's gate fails both w1 and w2.
- Runs: off 20261003_213031 (i2), 20261003_223152 (i3); w1 20261003_213033 (i3), 20261003_223150 (i2); w2
  20261003_233543 (i2), 20261003_233308 (i3). All ended; nothing of this chain is running.
- Key track samples: `C:\ssbot\sandbox\key_track_sample` (off, w1, side by side, README.txt).

### Open

- STUCK at boss HP <= 15 after one hit (h 2): the bot never attacks again (the U rule treats every attack near the
  boss as a possible killing blow when boss HP <= 15); 3 in 175813, 1 in the w1 arm, 3 in w2. Pre-existing; offered as a
  separate task.
- Next for key economy (facts section 6): A/B the bounded rule (off vs `--key-cost 0.05 0.1 0.05`, >= 110 fights an
  arm, instances crossed, same seeds) and adopt only if `key_economy --arm off ... --arm w1b ...` reports
  `gate.adopt` true; if it fails, put the risk / stance terms into the class. Then: stance dead zone against 2-3 frame
  direction taps; candidates that keep the previous plan's first part (most presses are decided the tick they are
  sent); measure per view (the vision view was never measured; Bell Beast gate numbers predate the terms, and the
  playbook is off again, so they still hold).
- The planner's CONTINUE row shifts the previous plan by 1 frame even after a late tick skipped frames (the key terms
  use the real shift); harmless so far, not changed.

## Chain X - EXCLUSIVE post-deploy checklist and the pause campaign restart (branch worktree-wf_7f5f02aa-b80-1)

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_7f5f02aa-b80-1`, from main ee64458. Instance 4 (port 47021) only;
seeds 118000-121999 (campaign 118000-121899, this chain's checks 121900-121954). Deployed DLL: main's oracle of
2026-10-04 00:25 (EXCLUSIVE). Facts: docs/facts/1.0.30000/pause_quit.md 8.1 (checklist results) and 8.2 (campaign).

### Done

- Checklist steps 3-9 on instance 4, all passed: HELLO action_flags ["exclusive"]; input.stats hold.released_early
  (0 at start) and the new `exclusive` counter; `m2_exports --skip-fight` all PASS; plain ACTIONs never grow
  released_early (4 plain eval fights, 15,058 ACTIONs: exclusive and released_early unchanged); brain-lost tap
  lands alone (latched 0x4000 only), also when the last ACTION pressed Up 1 frame before the tap (2 of 8 reps:
  cut by QueueExclusiveCutAll, released_early +2); pause block 20261004_014531 (keys 19, menu 21): 40 / 40 paused
  and on the main menu, latency max 3 frames, 0 game keys on the pause frame or in menus, 0 unpauses, 0 wrong
  submits, every loop key run >= 2 frames, released_early +20; low-HP 20261004_020857 (10): h 1 3 / 3 at G + 1 inside
  the i-frames, 0 Binds; h 2 7 / 7 Binds completed, 0 hit, 7 CLEAR, 0 quits.
- 3fdd8af: `m1_harness` hello checks action_flags / released_early, `lost` checks the tap lands alone, new
  `lost_late` section; `pause_stress` `loop_key_runs` / `loop_key_runs_short`; `combat_run.back_into_slot`: the way
  back into slot 1 (start and after every real quit) is tried 3 times with one recovery step between (new game's
  opening -> skip, then load the encounter savestate; no control -> savestate; paused -> Continue). Tests:
  tests/test_combat_run_retry.py (5) and test_combat_run_start / test_pause_stress / test_import_firewall pass.
- Cause of chain H's 07:13 death (recording 20261003_010522 i4_028): the slot-select Enter started a NEW GAME
  (Opening_Sequence, no hero; the save select read slot 1 as empty for that one press), and load_slot waited 120 s.
  Why the slot read empty is unknown. The new-game recovery path is tested only against a stand-in game.

### Running

- 10^4 pause stress campaign on the EXCLUSIVE DLL: worktree `C:\ssbot\live_pq_3fdd8af` (3fdd8af = main ee64458 + this
  chain's tools and retry; numba prewarmed), instance 4, seeds 118000-121899 (3900 trials, about 33 h), run dir
  `C:\ssbot\data\runs\m2\20261004_021933_BellBeast_eval_planner_oracle_inject`, launcher log
  `C:\ssbot\sandbox\pq_campaign_x.log`, started hidden (Start-Process -WindowStyle Hidden) with
  `C:\ssbot\sandbox\pq_campaign_start.cmd C:\ssbot\live_pq_3fdd8af 118000 3900 C:\ssbot\sandbox\pq_campaign_x.log`.
  Stop (graceful, after the current trial): from `C:\ssbot\live_pq_3fdd8af\brain`:
  `..\scripts\uv.cmd run python -m ssbot.tools.combat_run stop C:\ssbot\data\runs\m2\20261004_021933_BellBeast_eval_planner_oracle_inject`
  (or STOP_AGENTS). It holds SsOracle.dll on instance 4. Summarise with `pause_stress <run dir> --quiet --json
  <run dir>\pause_stress.json` (loop_key_runs_short must stay 0) and `lowhp_check --q1 <run dir>`, below normal.

### Next

1. Watch the campaign's worker_i4.log for "back into the sandbox slot failed": the first live retry tells whether
   the new-game recovery works in the real game (DebugMod savestate load from the new game's Tut_01 is untested).
2. Forum instances: checklist step 5's room.battles / allies check was not run (not this chain's instances).
3. Optional (lead): the Python key guard still waits 0-2 frames (19 / 19 in-flight-key trials waited); with
   EXCLUSIVE live it could model EXCLUSIVE (keys_clear always true) after a control block with the guard off.
4. Merge 3fdd8af and the docs into main; the campaign's code is main ee64458 plus these tools.
## Task D - Forum human demo analysis (branch worktree-wf_7f5f02aa-b80-2, offline, no game instance)

### Done (committed)

- `brain/ssbot/tools/forum_demo.py`: one streaming pass over a human_session recording (per-frame hero / input /
  room.battles / compact live enemies, all events, full entities around each hit taken; `--cache` pickles it); attempts
  = "Battle Scene" instances (death / clear / left); per attempt: waves and game-time durations, every mask lost (source
  -> type, collider or projectile, attack family via FORUM_SPECS, multi-hit chains, hero position / anim / contact,
  enemies in play and damage-collider distances to hero.box), heals and Bind starts, kills and killer (hero / Garmond /
  Cogfly / bell), nail clashes, technique use, pre-wave positions, key presses (key_economy's count). `--random-runs`
  adds the data policy's Forum runs (wave durations, hits per wave from each recording's events.jsonl). Tests
  `brain/tests/test_forum_demo.py` (3).
- `docs/facts/1.0.30000/forum_human_demo.md` (Chinese): summary for the lead at the top, per-attempt table (46),
  per-wave human vs random policy, hits / deaths by attack family, what the person was doing when hit, heals / deaths,
  kill order, technique use, pre-wave positions, keys, conclusions, implications for forum_planner_plan.md and K1.

### Key measurements

- 46 attempts (40 Reaper fo_A, 6 Wanderer fo_W), 46 deaths, best wave index 6 of 14; index 0 (Reed + Envoy +
  Choristor, no Garmond: he always enters 4.0 s after index 1 starts) is where attempts end: 22 / 46 deaths, median
  3.5 net masks per cleared index 0, 4 of 7 index-4 starts at 1-2 masks. Its 70 % hit share is mostly exposure (65 %
  of fight time): hits / min index 0 11.3, index 3 / 4 / 5 9.9 / 11.8 / 15.7. No data for waves 7-13.
- 10.5 hits / min (11.7 masks / min), 1.34 heals / min; the random data policy takes 13-20 hits / min in the same waves
  (the person 43-54 % fewer at index 0-1, about 25 % fewer at index 3-4).
- Hits per enemy-minute in play: Minister 6.6, Envoy 5.75, Clawmaiden 5.05, Reed 4.77, Choristor 4.73 (Choristor /
  Reed / Envoy = 89 % of hits and 88 % of enemy time). Deaths: Choristor 19, Reed 10, Clawmaiden 6, Minister 6,
  Envoy 3; every complete multi-hit chain cost 2 masks (48 / 48).
- 45 % of hits while attacking or in attack recovery; another damage collider within 2 u at only 12 % of hits, but
  3 enemies in play at 237 / 437; 20 / 46 deaths with full silk; 14 deaths with no heal (11 started at silk 9, 8 kept
  silk 9 throughout); 39 / 46 attempts start at 7 masks + silk 9, 7 at silk 1 (2 loads, 5 respawns); Cogfly and
  Silkspear never used; 164 incidental nail clashes (Envoy charge 50); keys 2.55 / 3.80 per s.
- Review fixes: per-type exposure (enemy-seconds in play per attempt), multi-hit chains closed after 90 frames
  without a Final Hit (chain_cut), death -> next start gaps only within a session, interpolated percentiles (medians
  changed slightly: Wanderer index-0 kills 7.8 / 6.6 / 17.3 s), start / lowest silk per attempt. Tests: 4.

### Next

1. Support certification order by wave: index 0 (Choristor / Reed / Envoy; the Envoy point savestate of R1 item 5
   earlier), then index 3-4 (Clawmaiden / Bellbearer / Minister), then Maestro / Tiny / Clapper.
2. R4 A0 baseline: report hits / min per wave index 0-4 against the person's 8-12 / min and the random 13-20 / min.
3. K1 loadout A/B candidates from the demo: Wanderer, Cogfly in index 0 on the Reed, Silkspear on the Reed.
4. A new demo: `..\scripts\uv.cmd run python -m ssbot.tools.forum_demo <session> --json out.json` (9 min scan ~8 s).
## Task "STUCK at 15 HP" - the killing-blow deadlock at h 2 (branch worktree-wf_9520bd11-c70-1)

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_9520bd11-c70-1`, branch `worktree-wf_9520bd11-c70-1`, from main
7733c98. First round 54d7e67 / 9b42247 / af8a215 (per-attack damage bounds, certified kill, QS); fixer round after the
review f140a49 .. c67e4c1 plus docs. Instances 0 and 1 (oracle, Bell Beast), seeds 115000-117999 (used 115000-115110,
115300-115460 for the kill checks, 115500-115639). Facts: docs/facts/1.0.30000/pause_quit.md sections 9 (first round)
and 10 (fixer round). Lead decision 2026-10-04: the certified killing blow at h >= 2 below full HP is approved; DESIGN
3.7.2 I3 (exception and its conditions), 3.7.3 YELLOW, 3.5.4 U and review row 47 updated.

### Done (fixer round)

- `combat/hero_damage.py`: the game's damage formula with every RoundToInt bounded up (DamageStack adds its
  multipliers), the fixed 5 damagers, the target's damage scaling per enemy type and needle level (audited; unknown:
  unbounded), the Wanderer crit after scaling; vision without an inventory audit takes every needle level.
- `tools/kill_window.py` + `knowledge/1.0.30000/kill_windows.json`: game time from the killing hit to the first
  pausable frame per freeze type (BossDeathSlow 0.1668 s / 330 kills, EnemyBattleEndSlow and BigEnemyDeathSlow 0.794 s),
  the kinds per encounter, and the hero's needle-damage dealt -> dmg audit per enemy type (Song Heavy Sentry 1.13-1.167
  at needle 1). Rows: `C:\ssbot\sandbox\kill_window_rows.json`.
- `combat/safety_filter.py`: KillKnowledge (window per encounter; unknown: the longest), in-flight kills (ranked, not
  vetoed), released_rise; `combat/planner.py`: the killing hit's own branches (`_kill_branches`: recoil / stop / bounce
  on the earliest and latest hit frame, best 12 plans), KillPlan on the chosen plan, idle_clear, kernels warmed.
- `train/planner_policy.py`: the kill commitment (the chosen kill plan played by game time through the slow motion; not
  for an uncertified blow at full HP with h >= 3); `train/episode.py` acts through it (`SSBOT_POST_CLEAR_S` for
  checks); `train/supervision.py` kill_inputs is the one source for the allowlist and the L0 filter.
- `safety/supervisor.py`: QS needs the no-input path clear for 0.4 s and progress clears the latch first; vision input:
  FOCUS_LOST alone does not block pausable unless the sink is the foreground one.
- `train/hit_injection.py`: `SSBOT_INJECT_BOSS_HP_MAX` / `SSBOT_INJECT_MAX_SILK` (the certified-kill check).

### Measured

- Certified kill at h 2 live (20261004_043850, d356c8e, injected hit to 3 HP at boss <= 15 HP): 24 CLEAR, 0 WOULD_DIE,
  23 / 23 kills at h 2 certified; the commitment ran through the whole slow motion; the executed hero box stayed within
  0.405 u (x) / 0.454 u (y) of the certified branch (before the branch and released-rise fixes: 1.9 / 5.5 u, runs
  041626 / 042718). 4 of 23 then took an attack bell 130 frames after the kill (14-15 frames after the window) -> Q1.
- Plain live (20261004_045230, d356c8e): 104 CLEAR, 0 STUCK, 0 QUIT, 0 WOULD_DIE, 1 hit, time to kill p50 59.7 s,
  planner p50 4.31 ms / p99 median 10.8 ms. Confirmation on c67e4c1 (20261004_055131, 20 episodes): 20 CLEAR, 0 hits, 0 commitments, time to kill p50
  58.2 s.
- Offline replays (`C:\ssbot\sandbox\stuck_replay_fix3*.json`): the 8 STUCK episodes attack on every tick; with the
  boss read as 5 HP 75-88 % of ticks have a certified kill plan and QS quits 8 / 8 at a safe frame at 20 s; the
  degraded_dust replay now reaches QS (it never had a pausable frame before the FOCUS_LOST fix).
- Tests: 957 passed, 1 skipped, 1 xfailed, 1 failed (test_support_query_budget timing 3.94 ms under load; untouched).

### Needs the lead

- Post-kill attack bells: a kill during Burst Out leaves two launched attack bells that land about 130 frames later;
  the forecast after the boss's death does not cover them (unpredicted). Not in the certified window, but it costs a
  Q1 quit after 17 % of the h 2 kills and a 2-mask hit after full-HP kills in a run that keeps acting. Fix in the
  forecast (keep launched bells in the support after Death Broadcast) before the run manager acts after kills.
- Vision has no inventory audit: every needle level counts, so the nail is unbounded in vision for Bell Beast (only
  needle 0 audited) and every attack in YELLOW needs the certification. A needle-level audit is needed for phase 2.
- FOCUS_LOST fix changes vision training: Q4's "pausable GREEN frame" can now hold there; re-run the vision gate after
  merging before quoting its old numbers.

### Next

1. The post-kill attack-bell forecast (above), then re-run the certified-kill check (start script
   `C:\ssbot\sandbox\stuck_fix2_kill_start.cmd`, `SSBOT_INJECT_LEAVE_HP=3 SSBOT_INJECT_BOSS_HP_MAX=15
   SSBOT_INJECT_MAX_SILK=8 SSBOT_POST_CLEAR_S=2.5`, `--inject-hits 1.0`) and summarise with the kill commitments' path
   check (decision log rows of mode KILL_COMMIT: commit.planned_now / planned_now_hit / planned_now_kill vs box).
2. Audit damage scaling before each new encounter or needle level (`python -m ssbot.tools.kill_window <runs>
   --write-knowledge`; add the scene to ENCOUNTER_SCENES / NEEDLE_BY_SCENE).
3. Remove the live checkouts `C:\ssbot\live_stuck_f140a49` (at c67e4c1; the name is stale) and
   `C:\ssbot\live_stuck_9b42247` when no longer needed (`git worktree remove --force`).

## Task "post-kill forecast" - keep dodging after the boss dies (branch worktree-wf_8f2a901f-a0c-1)

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_8f2a901f-a0c-1`, from main d1f3c46. Code 5a97e0f + fd18ae6 (tool fix,
test), fixer round c1e971b; docs after each. Instances 0 and 1 (oracle, Bell Beast), base seeds 122000 (smoke), 122100
(kill check), 122500 (200 plain), 123500 (first gate, stopped), 124000 (gate on c1e971b). Facts: `docs/facts/1.0.30000/post_kill.md` (Chinese); DESIGN §3.9.4 (CLEAR with the post-kill
tail) and §3.7.2 I3 (the window's support holds what outlives the boss); M2.md status line; pause_quit.md 10.7 marked
fixed.

### Done

- `combat/forecast.py`: after Death Broadcast (oracle view) every attack bell in the export is a DetBell on its exact
  path (registry physics from its position and velocity; life = first bounce + 2 s End Timer + 0.05 s), and the BB_BURST
  death tail's attack-bell union is no longer placed once both bells are exact (`SSBOT_DEAD_ATK=0`: the old way);
  drop bells in "Cancel" (the death cancels a bell in its Antic) count as at rest. The fight (boss alive) is unchanged.
- `train/planner_policy.py`: `act_after_clear = True` (the planner plays through the tail); a death without a kill
  commitment keeps the last plan by game time through the slow motion (`_post_kill_commit`), then the planner ticks;
  `stats()["post_kill"]` (ticks, planner ticks, FORCED_RISK after the death).
- `train/episode.py` + `train/encounters.py`: `Encounter.tail_quiet_s` (Bell Beast 2.0): CLEAR only once no damage
  source (`live_threats`: an enabled damage collider, or a drop bell in Antic) has been live for 2 s of game time after
  the kill (FightTap counts every STATE); leaving the room ends it too; > 15 s: STUCK; a supervisor quit before the
  tail's end: QUIT ("quit after the kill"); a lethal hit: WOULD_DIE. New record fields kill_s, f_kill, tail_s,
  tail_threat_s, tail_threats, tail_hits, tail_hp_lost, tail_end; `combat_run summary` uses kill_s for the time to kill
  and adds `post_kill_tail`. `SSBOT_POST_CLEAR_S` still gives the old fixed window (and turns the tail off).
- `tools/post_kill.py`: scan (what is live after each kill, exact-path error, Cancel), clears (past CLEARs: live source
  at the window's end, the standing hero's exposure), cover (post-kill contacts vs the certification's forecast and the
  post-death one).

### Measured

- Recordings (4,603 kills): Burst Out kills (1,140) always leave both attack bells in flight; 114 of 545 Dig In kills a
  falling drop bell; body contacts <= 0.0202 s of game time after the kill; 1,222 Antic -> Cancel, all on kill frames;
  exact paths after the kill within 0.032 u (2,280 bells).
- Support recall on the 2.5 s post-kill recordings (041626 / 042718 / 043850, L 3): post-kill attack-bell contacts
  uncovered 104 -> 0; the forecast the kill was certified with (boss alive, frame before the kill) covers all 105
  post-kill contacts (0.017-1.116 s ahead).
- Kill check at h 2 (20261004_064120, 24 episodes, injected to 3 HP): 24 CLEAR, 24 / 24 certified, 8 with bells after
  the kill, 0 hits in the tail (before: 4 of 23 Q1 quits), 0 FORCED_RISK in 3,234 post-kill planner ticks.
- Past CLEARs (`post_kill clears`, counts corrected in the fixer round; they match the attempt rows): oracle eval 2,872:
  none changes outcome (all full-HP kills), 772 would have had a longer tail, 714 would have been hit standing still;
  injection runs (237 CLEARs): the 121 "quit after the kill" CLEARs (75 Q1, 6 of them QUIT_EMULATED; 46 injected QF)
  become QUIT, 6 of them the post-kill bells' Q1 (042718 i1 ep5 / ep7, 043850 i0 ep6 / ep7 / ep9, i1 ep5); the 7
  standing hits at HP <= 3 are those 6 plus 042718 i0 ep8, whose real post-kill bell hit (HP 5 -> 3) is already in its
  hits: no further outcome changes. Vision view 1,253 / 361 live / 359 standing, none at low HP.
- Plain live run with the tail (20261004_065707, fd18ae6, 200 episodes, base seed 122500, --real-quit 0.2): 200 CLEAR,
  0 QUIT / STUCK / WOULD_DIE; 8 hits in the fight (0 unpredicted), **0 in the tail**; 56 kills left live sources (51
  both attack bells, 5 a falling drop bell), the last one live <= 2.94 s after the kill, tail p50 2.015 s / max 4.95 s
  (game); 39 FORCED_RISK ticks in 7 tails (bells landing just after a full-HP kill's slow-motion commitment), no hit;
  2 certified kills at h 2; time to kill p50 58.0 s (48.2-76.9); planner p50 4.50 ms, p99 median 11.5 ms, max 15.5 ms.
- Full-HP kills' commitments (the last plan sent, uncertified) leave the plan by up to 2.4 u (x) / 7.4 u (y): the
  killing hit's own effect (a down spike's bounce off the boss) is not in that plan; certified ones stay within 0.47 /
  0.70 u of their certified branch (kill check).

- First gate (`C:\ssbot\data\runs\m2\20261004_085210_BellBeast_eval_planner_oracle`, fd18ae6, base seed 123500): stopped at
  09:06 by the lead's half-speed demo (STOP in the run dir, DEMO_SOON) after 13 episodes per instance: 26 CLEAR, 2
  fight hits, 0 tail hits, 7 kills with live sources. With 20261004_065707 that is 226 episodes on fd18ae6, not 500.

### Fixer round (code c1e971b)

- `train/episode.py` `live_threats`: an enabled damage collider counts when eff != 0 (was > 0): the oracle exports eff -1
  for multi-wounder FSM sources (as `ipc.ents.is_threat`), which would otherwise never keep a tail going (the Forum).
  No change for the Bell Beast: re-scanning all 256 tail kills (063700, 064120, 065707, 085210) with it gives the
  same last live source as the live `tail_threat_s` in 256 / 256.
- `tools/combat_run.py`: `config_fp` also hashes the SSBOT_* switches when any is set (`SSBOT_POST_CLEAR_S` turns the
  tail off, `SSBOT_DEAD_ATK=0` the old post-death forecast, the A/B toggles); without switches it is the old hash
  (065707 stays e4a26680c027). The switches go into config.json and every row (`env`). `summary` refuses to pool rows
  of different fingerprints (exit 1, `refused`) unless `--mixed`.
- `tools/post_kill.py clears`: skips rows made with the tail (so `--glob` over all runs is fine); each CLEAR says
  whether it ended "quit after the kill" and which real post-kill hits its recording shows; the summary splits the
  low-HP standing hits by those (`standing_low_hp_already`).
- Tests: full suite 1004 passed, 1 skipped, 1 xfailed (test_support_query_budget deselected as before: a timing budget
  that fails under machine load); new `tests/test_combat_run_fp.py`, eff -1 / 0 cases in `test_live_threats`.
- Facts: post_kill.md section 5 corrected, section 8 (this round); M2.md status line corrected.

### Gate on c1e971b

- From scratch (the fd18ae6 episodes have another fingerprint): 500 episodes, instances 0 and 1, 250 each, base seed
  124000, `--real-quit 0.2`, oracle view, checkout `C:\ssbot\live_postkill_c1e971b` (commit c1e971b; the commits after
  it are docs only). Start: `C:\ssbot\sandbox\postkill_gate2_start.cmd` (detached and hidden; it does nothing while
  STOP_AGENTS or DEMO_SOON exists). Log `C:\ssbot\sandbox\postkill_gate2.log` (prints the run dir, ends with
  POSTKILL_GATE2_DONE; about 4.7 h). Summary: `combat_run summary <run dir>`; stop: `combat_run stop <run dir>`.
- Status: RUNNING. Started 09:53 once DEMO_SOON was gone (it was there 09:06-09:52):
  `C:\ssbot\data\runs\m2\20261004_095304_BellBeast_eval_planner_oracle`, code_rev c1e971b, config_fp 14d5015e849a,
  env {} (no SSBOT_* switches). First 6 episodes: 6 CLEAR, tail_end "quiet", 0 tail hits. Expected end about 14:40.
  If it is stopped early (STOP / DEMO_SOON), restart the missing episodes from the same checkout with a new base seed
  outside 124000-124249 (for example 124300) and pool only rows of config_fp 14d5015e849a.

### Next

0. Read the gate on c1e971b when it ends (its own run dir only; `summary` refuses other fingerprints); post-kill
   numbers in its summary's `post_kill_tail`.
1. Turn the tail on for the Forum (`tail_quiet_s`, the runes / bombs / dying Clappers as live sources) after checking
   its recordings the same way (`post_kill scan` is Bell Beast only now: BOSS / SCENE constants).
2. Vision view: a cancelled drop bell stays armed in the vision tracker up to BELL_TTL_S (8 s) after the death (the cue
   just stops); harmless (more support), but the vision view's post-death support is not checked live.
3. Full-HP kills: their slow-motion commitment is the last plan without the killing hit's branches; certify every
   possibly killing blow's branches, or prefer a certifiable plan under I3 too, if the tail's FORCED_RISK matters.
4. After the death no new drop bell can arm, but the drop-bell unions of the tails (t_from 1.2 s) are still placed:
   extra support beyond the planner's 0.8 s (the tactics' risk map sees it); left as is (the kill check and the 200
   measured this support).
5. Remove the live checkout `C:\ssbot\live_postkill_c1e971b` after the gate (`git worktree remove --force`); the
   5a97e0f and fd18ae6 checkouts are already removed.

## Task R1 - Forum plan round R1: wave starts, targeted collection v2, wall climb, speed-up check (branch worktree-wf_6dcc3810-3d5-1)

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_6dcc3810-3d5-1`, instances 2 and 3 (ports 47019 / 47020), seeds
127000-131999 (used: 127000+, 127100, 127200, 128000+, 129000+, 130000-130200, 130500+, 131000+; `--same-seeds` keeps
them in range), savestates `fo_r1_*`. Facts: `docs/facts/1.0.30000/forum.md` section 13 (R1). Plan:
`docs/plans/forum_planner_plan.md` §5 R1. Main (with R0) merged into the branch at e1a54a9.

### Done (committed)

- Wave starts (`brain/ssbot/train/wave_start.py`): a DebugMod savestate taken during wave i restarts the battle at wave i
  on load (DebugMod RoomSpecific keeps "BattleScene|Battle Scene|<currentWave>" and patches DoStartBattle to
  StartWave(currentWave)). `fo_r1_w0` .. `fo_r1_w13` made by one policy skip from fo_A (`make_wave_states`). Encounters
  `Forum_A_w<i>` (timebox 180 s); `combat_run --encounter` takes a comma list (rotates per episode). What a load does
  not give (forum.md 13.1): the helper from wave 2 on (a w1 load does bring Garmond); room.battles reports wave i at the
  battle start, startDelay(i) (1.0-3.0 s measured) before its members are activated; the never-run members of waves
  0..i-1 stay children of their wave objects, so DoCheckEnemiesNew is inflated (a w2 load starts wave 3 only after a
  wave-2 kill, 59.7 / 75.05 / 65.95 s in the first run, instead of 1.6 s).
- Fixer round (8a03afb): the wave-start intro waits for the activation (room.battles currentEnemies > 0) and moves the
  tap's battle start there (`GauntletTap.rebase_start`; AttemptRecord intro: battle_start_f, active_f, activation_s);
  it calls the new oracle RPC `battle.prune` first (detach + destroy the HealthManager children of waves 0..i-1; not
  deployed: records say ghosts "unpruned"). Forum_A_w2 is out of the rotation until the deploy; the first run's three
  w2 episodes are listed in `C:\ssbot\data\runs\m2\20261004_111158_Forum_A_w2_mix_data2\exclude_w2_ghosts.json`
  (behaviour_build --exclude-fights).
- Oracle (both built `-p:Deploy=false`, NOT deployed): 06a7c2b `time.scale` > 1 through DebugMod's TimeScale (the game
  clamps its own controls to 1) and `battle.wave {wave}`; 8a03afb `battle.prune`.
- Wall climb (`brain/ssbot/train/climb.py`): probes 27 / 27; in the policy (first run, 36 wave-start episodes) 159 real
  climbs, 144 to the top (91 %, p50 2.39 s); 61 more CLIMB segments began at the top and are not climbs (now flagged
  `start_top`).
- Targeted data policy v2 (`brain/ssbot/train/forum_policy.py`, `--policy data2` / `data2_envoy`, `idle`). Fixer round:
  the Envoy protection counts the hero's velocity over 0.35 s and blocks down slashes over a protected body (the first
  run hit the Envoy at <= 20 HP 69 times in 106 episodes, 49 episodes, 5 kills; mostly down slashes and dash slashes);
  per-frame draws are hazards per game second, rest in game time; pocket share 0.5 (was 0.85: 60 % of the w7 / w13
  time on the wall); `policy.segments` [frame, tactic, target, pocket, protect] and `protect_hp` in every record;
  `IdlePolicy` (no input) for the speed check.
- Never-seen moves are unreachable (FSM structure): Envoy HopSlash (Hop Up? 2407 -> Slash Antic 2407), Bellbearer Throw
  Antic Quick (Rethrow? 910 -> In Range), Maestro Point (Attack Choice 794: Fire 556, Defend 238, Point 0); the Forum
  Envoy's entry is its ambush.
- Tables (R0's builder, fixer round): candidate covariate `hero_height` for the Forum specs (bins < 1 / 1-5 / >= 5 u
  above the floor; Bell Beast unchanged): on the first run's 9 Clapper fights it is kept for Clapper Idle and Walk (the
  pocket: Idle at 3-10 u, 0 / 494 Evade or Dmg Attack in the pocket vs 83 / 237 on the ground). Protected types:
  `knowledge/1.0.30000/enemies/forum/hero_caused.json` (fsm.graph, 9 types: states with a TOOK DAMAGE / BLOCKED HIT /
  CANCEL MULTI HIT exit); a type in a record's `policy.protect` loses its decisions out of those states at hp <=
  protect_hp and its dwells in them (GauntletBuilder._drop_protected). `run_fights` carries unit / protect / segments.
- Tools: `forum_r1_audit` (fixer: `boundary_r0` like-for-like with R0's Boundaries product, `clapper_dec` by hero place,
  same-enemy clawline hits, Poisson P under fliers, `climbs_real`), `forum_speed_check` v2 (dwell on the coarsest frame
  grid as integer steps, 0.2 s speed windows with both arms read on the coarse frames, choices by distance bin, Holm
  with extended permutations plus the 99 % binomial bound, `--simulate-b K`), probes `forum_r1` (midsave / skip /
  states / check / climb / fsmgraph). Tests `brain/tests/test_forum_r1.py` (20).

### Measured (forum.md 13; first run = frozen 1c374f8, runs 20261004_111158_*: Envoy 106 episodes 1.56 h, waves 36 / 1.71 h)

- Near-boundary decisions, R0's definition (within 1 u of R0's boundary_u), per game hour R1 vs R0: Envoy slash 1011 vs
  25 (chosen 233 vs 5.8), Choristor slash 4369 vs 445 (chosen 34.7 vs 3.5), Clawmaiden slash 77 vs 45 (24.6 vs 16.8),
  Minister evade 408 vs 186 (12.9 vs 5.1), Clapper slam 521 vs 762 (16.4 vs 44.5). The chosen share per decision is
  R0's in every family (an enemy property); the first round's "3-47x" counted any entry into an attack start.
- Clawline: 203 presses, 75 harpoon hits, 5 hero hits within 0.5 s, all 5 from the hooked individual (nearest-body
  match). Under fliers (Poisson at the near rate): Bellbearer 0 in 51.8 s vs 4.08 expected (P 0.017); Minister 0 vs
  0.85 (P 0.43); Reed 6 vs 6.9 (no gain); Tiny 44 vs 50.8. Bells: 289 CLASH swings at bells; the bell FSM entered Nail
  Hit 109 / Tink 105 times from any swing (not a per-swing rate). Pocket 1232 s: Clapper jump 127 / jump cast 121 /
  cast 117 / evade 117, slam 0, Clapper hits 0.
- Speed check calibration (074533 vs 074719, 8 + 8 fights): 1x vs 1x dwell 7 / 270 (cap 22), speed 6 / 114, choices
  0 / 37, hitbox 0.4 %; 1x vs simulated 2x dwell 10 / 270, speed 5 / 112, choices 0 / 39, hitbox 0.4 %; no Holm hit
  anywhere. Without the grid the simulated 2x fails (136 / 270 dwell; the first tool 155).

### Running

- Nothing. The fixer's collection (`C:\ssbot\sandbox\fo_r1f_run.cmd`, hidden cmd, frozen code
  `C:\ssbot\live_fo_r1f_8a03afb`, a git worktree of 8a03afb) started 13:13 and stopped itself at 13:36-13:38 when
  `C:\ssbot\sandbox\DEMO_SOON` appeared ("human practice 0.5x Forum"): instance 2
  `C:\ssbot\data\runs\m2\20261004_131323_Forum_A_w0_data2_envoy` (23 protected Envoy episodes), instance 3
  `C:\ssbot\data\runs\m2\20261004_131323_Forum_A_w4_mix_data2` (8 wave-start episodes). After the demo (DEMO_SOON
  gone), restart hidden: `Start-Process cmd.exe -ArgumentList "/c C:\ssbot\sandbox\fo_r1f_run.cmd i2w" -WindowStyle
  Hidden` (instance 2, wave starts 7.5 h, seeds 130500+) and the same with `i3` (instance 3, 9 h, seeds 131100+); logs
  `C:\ssbot\sandbox\fo_r1f_<part>.log`; stop with STOP_AGENTS / DEMO_SOON or `combat_run stop <run dir>` (from
  `C:\ssbot\live_fo_r1f_8a03afb\brain`).
- The first round's chain (`fo_r1_chain.ps1`) is gone: its PowerShell hosts had died before 13:00 (no "end" lines) while
  their workers ran on; the fixer stopped both workers gracefully (STOP files) at 13:00.

### Needs deploy

- Oracle at 8a03afb (`time.scale` > 1 and `battle.wave` from 06a7c2b, `battle.prune`), built with
  `-p:Deploy=false`; deploy when no instance runs (the user closes the game windows).

### Next

1. After the deploy, `forum_r1 check --waves 2,3,4,9,10` (battle.prune: a w2 load starts wave 3 about 1.5 s after the
   activation; prune lists the earlier waves' members), then put Forum_A_w2 back into the rotation.
2. After the deploy, the 2x check: same seeds on two instances, at least 8 + 8 gauntlets, first
   `combat_run run --instances 2 --encounter Forum_A_w7,Forum_A_w13,Forum_A_w4,Forum_A_w6 --policy idle --same-seeds
   --seed 131500 --episodes 8 --time-scale 2` and the same with `--instances 3` at 1x (no input: the policy's action
   latency doubles at 2x), then with data2; `forum_speed_check --a <1x> --b <2x>` (`perm_verdict`: dwell, speed,
   choices, hitbox all match, none underpowered). Even then a 2x instance fills every other 1/60 s state-time bin, so
   the support templates need their own check.
3. After the deploy, `forum_r1 skip --method oracle --wave 13` (battle.wave) and check that Garmond comes in.
4. Rebuild the Forum tables with R0 + R1 (`behaviour_build --encounter Forum <runs> --exclude-fights <w2 list>`): check
   the build report for `hero_height` among the conditioners and the `protected Song Pilgrim 01: ... dropped`
   counters; keep R1 provenance for an ablation (R1 dominates the Envoy: 2407 slashes in 1.56 h vs R0's 692 in 25.4 h);
   mark HopSlash, Throw Antic Quick, Point and the Envoy Wake entry as structurally absent.
5. Restart the collection after the demo (Running). The protection fix is measured: run
   20261004_131323_Forum_A_w0_data2_envoy, 23 episodes, the Envoy brought to 20 HP in every one (46 hits), then 0 hits
   and 0 kills (first run: 69 hits in 49 of 106 episodes, about 15 expected in 0.38 h).
6. `gauntlet.WAITING_STATES` lacks "Dead" (the Maestros' parked Tinies): live_enemies counts nine parked Tinies in play
   from the load on; v1's GauntletDataPolicy targets them. R1 code filters them (`wave_start.fighting`); fixing
   live_enemies itself changes other tools' numbers (left for a reviewed change).

## Task R1 close-out - post-deploy checks, the 2x check, collection restart, R0 + R1 tables (branch worktree-wf_5031b357-209-2)

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_5031b357-209-2` (from main 56845a9; deployed oracle = 56845a9,
`SsOracle.dll` md5 11E34633...). Instances 0-3 (never 4). Seeds 131500-131515 (speed check), 131900-131902 (probes),
132000+ / 133000+ / 134000+ / 135000+ (wave starts i2 / i3 / i0 / i1), 136000+ / 137000+ (full gauntlets i0 / i1).
Facts: `docs/facts/1.0.30000/forum.md` 13.9 onward. Offline outputs (not in git): `C:\ssbot\data\m2_forum_r1c\`.

### Done (committed)

- Post-deploy checks (forum.md 13.9): HELLO and `time.scale` 2 -> dt 1/30 -> 1 on instances 2 and 3 (new probe step
  `forum_r1 hello`); `battle.prune`: w2 -> wave 3 about 1.5 s after the activation (4 probe loads 1.52-1.53 s as frames / 60,
  which undercounts game time right after a load; the first collection episode 1.565 s of game time), ghosts 5 / 7 / 8 / 17 / 20 for w2 / w3 / w4 / w9 / w10; `battle.wave` skips to 6 (5.1 s) and 13
  (16.7 s) with Garmond coming in. `forum_r1 check` records the wave clock at frame resolution. Forum_A_w2 is back in
  the rotation (`C:\ssbot\sandbox\r1c_collect.cmd`).
- 2x check (forum.md 13.10): NOT passed, 2x not adopted, no 2x data in any table (the Clapper's event-ended states end
  one 2x frame apart in both policies; controls pass, injected +1/30 s caught). `combat_run`: the timebox is divided by
  the time scale (414fb1a), `set_time_scale` waits out a momentary Time.timeScale 0 (28a9417); `forum_speed_check
  --inject / --a-slice / --b-slice` and per-type family totals (f656330, 3aa1019). Drivers
  `C:\ssbot\data\m2_forum_r1c\speed\run_checks.ps1`, `run_checks2.ps1`.
- `gauntlet.WAITING_STATES` has "Dead" (59e02a1, forum.md 13.11; every user of live_enemies / in_play checked, tests).
- Structurally absent moves marked (abad048, forum.md 13.12) and stamped into R0's committed tables (cb945b9,
  `behaviour_build --stamp-absent`; templates and decisions unchanged).
- R0 + R1 rebuild and recertification (forum.md 13.13): NOT certified, the new tables are not committed (R0's stay).
  The R0 + R1 build (288 fights, 30.07 h, 341,436 contacts) passes the development cross-fit like R0 (100 / 99.9997 /
  99.9997 %, the same Clawmaiden `Slash 5` miss); on 202 fresh fights (175,437 contacts: 38 full gauntlets, 132 wave
  starts with w2, the 32 1x speed-check episodes) fold 0's tables cover 100 % at L2 / L3 / L4 and fold 1's miss one
  contact at L3 and L4: `20261004_162411` i3/ep9 f482061, a blocked contact with `Slash Collider 1` reported on the
  first frame of `Slash 2` after a 2-frame `Slash 1` while the Clawmaiden lunged 0.66 u. The ablation (R0's tables and
  margins, same fresh fights) misses the same contact, so R0's "certified" (35 fights) does not hold on this data;
  with R1 fewer contacts need the tubes / candidates, the Minister charge margin rises to the 3.0 u cap.
- Tests: 1037 passed (the support-query budget test fails under this load: 3.88 ms p99 vs its budget; unrelated).

### Measured

- 2x (forum.md 13.10): idle 16 + 16: dwell 18 / 67 keys below 0.05 (cap 8), Holm 7; speed 19 / 42 (cap 6), Holm 4;
  choices 1 / 13; data2: dwell 20 / 115 (cap 12), Holm 4; speed 9 / 65 (cap 8), Holm 1; choices 0 / 24. Same Clapper
  keys in both (Air 27 -> 26 coarse steps, Slam 0 / 1, Spell Antic), mean shifts within one 1x frame; jump height
  equal (8.219 u), air time differs by the Air exit (fixer round: from FSM events, 28 steps 39 / 213 at 1x vs 26
  steps 13 / 203 at 2x); and the Tiny's Ready self-loop (fixer round, not seen by v2). Controls (wave-balanced halves) pass; injected +1/30 s dwell caught (Holm 21-24
  at 16 + 16), choice shifts below about 20 points and 10 % speed at 8 + 8 not caught.
- Wave starts: w2 -> wave 3 1.52-1.57 s after the activation with battle.prune (59.7-75 s before); records' frame-based
  wave times undercount game time for a second or two after a load (load-hitch frames).
- Collection rates at 1x under full load: full gauntlet about 12.5 min (38 in 4 h on two instances, all CLEAR), wave
  start about 3.3 min.

### Running (hidden; each run stops by itself on STOP_AGENTS / DEMO_SOON after its current episode)

- Collection at 1x from the frozen checkout `C:\ssbot\live_r1c_28a9417` (`C:\ssbot\sandbox\r1c_collect.cmd`, logs
  `C:\ssbot\sandbox\r1c_collect_<part>.log`), all data2 wave starts with Forum_A_w2 back in the rotation:
  - instance 0: `20261004_195019_Forum_A_w2_mix_data2` (6 h from 19:50; after its 4 h of full gauntlets
    `20261004_154609_Forum_A_data`, 19 CLEAR);
  - instance 1: `20261004_195800_Forum_A_w2_mix_data2` (6 h from 19:58; after `20261004_154612_Forum_A_data`, 19 CLEAR);
  - instance 3: `20261004_162411_Forum_A_w2_mix_data2` (9 h from 16:24).
  - instance 2: `20261004_155649_Forum_A_w2_mix_data2` RAN AT 2x (see the fixer round below), stopped 23:39; replaced
    by `20261004_233950_Forum_A_w2_mix_data2` (8 h from 23:39, frozen `C:\ssbot\live_r1cfix_ed65873`,
    `C:\ssbot\sandbox\r1cfix_collect.cmd i2`, log `r1cfix_collect_i2.log`, seeds 138000+).
  - Stop one: `cd C:\ssbot\live_r1c_28a9417\brain; ..\scripts\uv.cmd run python -m ssbot.tools.combat_run stop
    <run dir>` (instance 2's from `C:\ssbot\live_r1cfix_ed65873\brain`).
- Offline: nothing (pipelines done: `C:\ssbot\data\m2_forum_r1c\pipeline_build.done`, `pipeline_cert.done`; the
  pipeline's duplicate ablation step was stopped, its result is `recall_fresh_r0tables_early.json`).

### Needs deploy

- Nothing (no oracle change).

### Next

1. R2 (MultiForecast): the fresh miss is spatial, in a moving attack (the Clawmaiden's slash lunge): re-anchor moving
   attack families at the current position (R0 Next 2) or condition them on the path, then certify on fights none of
   the builds or certifications has seen (the 202 fresh fights of 13.13 are seen now). Do not set Forum `known` from
   `support_margins.json` (`certified: true` is R0's 35-fight result, contradicted by 13.13).
2. Next table build: R0 + R1 + R0's 35 fresh + this round's fresh fights except `20261004_155649` (2x) + the running
   collection (all 1x; the builder now leaves out non-1x fights with a warning); the
   candidate tables of 13.13 (`C:\ssbot\data\m2_forum_r1c\tables\forum`, stamped) can serve R2's development meanwhile.
3. (Done in the fixer round: the Minister charge margin at the 3.0 u cap was one mis-attributed contact, fixed in
   eeb550e; check the new counter "touching up to LAG_F before; this frame's exporters far" in the next build.)
4. A 2x retry only with a pre-registered equivalence criterion (one 1x frame), every type in 8+ fights per arm, and
   longer fights (forum.md 13.10, 13.15).
5. Records: wave times after a load in game time (sum of STATE dt), not frames / 60 (forum.md 13.9).

### Fixer round (after the review; forum.md 13.15; commits 04b6228 .. this one)

- REFUTED and corrected: the 2x difference is not only Clapper states. The Tiny's Control `Ready` self-loop runs on
  real time or frames (`Ready -> Ready` 953 -> 356 idle, real-time dwell equal, game-time dwell 1.80 -> 3.23 s).
  `forum_speed_check` v3 (04b6228): `visits` and `next` metrics, attainable p per key from the fights containing it
  (`underpowered_keys`), Clapper jumps from FSM events, `--inject trans`, `--a-units / --b-units`. An independent 1x vs
  1x control (153511 vs 16 wave starts of 162411, same four waves): nothing flagged, also with B coarsened to 2x;
  injected +1/30 s dwell (Holm 33), Clapper-only (23), Clapper speed x1.1 (5) and the Tiny loop x0.37 (`next`, Holm 1)
  caught at 16 + 16; x0.6 / x0.8 and a 10-point choice shift not. 2x stays not adopted.
- Instance 2's "1x" collection `20261004_155649` ran every episode at 2x (Time.timeScale left at 2 by the 2x arm
  153211; `set_time_scale` did nothing at 1x). Stopped, fixed (ed65873: set and read back at 1x too,
  `time_scale_game` in the records, reset to 1 at the end of a scaled run; the Forum builder leaves out fights whose
  STATE dt is not 1x), restarted at 1x. All other runs of today checked by STATE dt: 1x. 72 of the 202 fresh
  certification fights were this run: the certification result does not change (the miss is in 1x run 162411), but
  do not use 155649 as 1x data anywhere (it can serve as a second-seed 2x arm).
- MI_CHARGE 3.0 u: one contact (111158 i3/ep10 f400125) attributed to the far Minister on the last frame of a blocked
  stretch; `GauntletBuilder._attribute` fixed (eeb550e; rescan of that fight: all 11 frames to the adjacent one).
  Pre-prune wave starts other than w2 stay in the build (ghosts are not exported; only composition / wave timing
  differ, keep them apart in composition products by code_rev 1c374f8).
- `GauntletDataPolicy.REVISION` 2 in the policy stats (e2b0873): v1 gauntlets from 59e02a1 on (incl. the 38 fresh
  full gauntlets) are a different policy version from R0's (the pocket test).
- Docs: 13.9 probe times labelled frames / 60; 13.10 Jump Antic rounding comparison (24 % expected vs 41 %), jump
  physics from FSM events, the 8 + 8 controls test only the binomial count; 13.13 fresh-set provenance.
- Open: whether the Tiny's Ready loop counts frames or wall-clock time (if wall clock, its 1x game-time rate depends
  on the machine's load: real / game 1.06 now); the next build must show the speed guard's counter at 0 for its
  run list.
## Task R2 - Forum multi-enemy forecast (branch worktree-wf_5031b357-209-1)

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_5031b357-209-1`, branch `worktree-wf_5031b357-209-1`. Offline
only (no game instance touched). Plan: `docs/plans/forum_planner_plan.md` §4.1 / 4.3 / 4.4 item 6 and the R2 row of
§5. Facts: `docs/facts/1.0.30000/forum.md` §14 (Chinese). Outputs (not in git): `C:\ssbot\data\m2_forum_r2\` (`r1\` the
R1 runs' contacts, `recall_*.json` / `*.log`, `consistency_*.json`, `proj_audit_10c.json`, `bench_*.json`, the `.cmd`
drivers). The production tables need `knowledge/1.0.30000/enemies/forum/*_hitboxes.npz` (gitignored; rebuilt by
`behaviour_build --encounter Forum`, copied into each frozen checkout by hand).

### Done (committed)

- `core/forum.py`: the Forum's static facts for run-time code (9 types, waves with spawn points, hazard owners / aliases,
  structurally absent moves, walls / floor / dome), tested against `knowledge.gauntlet_tables.FORUM_SPECS` and
  `train.encounters` (the import firewall keeps combat code off those modules).
- `combat/enemy_tables.py`: one template store for the 9 types (fine templates in arenas, coarse 0.25 u bases with time
  OR pyramids, per-bin bounding-box sparse tables), lazy npz reading and chunked coarsening (peak working set 1.94 ->
  1.1 GB), type tables without the structurally absent moves, tubes, chains, fold / production configurations.
- `combat/enemy_tracker.py`: EnemyTracker per enemy instance (SubjectTracker semantics; oracle: Control FSM events;
  VE: phase + body offset); HP from seen hits only (oracle amount, else the attack's price); a kill leaves its death box
  for 3 bins, no tail for the attack it cuts short, and keeps the tails of the attacks it finished (their thrown
  hazards outlive it: VE own-type recall needs them for the Clapper's rune slams / bombs).
- `combat/multi_forecast.py`: MultiForecaster / MultiForecast with the §4.3 interface (occupied, occupied_without,
  prob, t_min, committed, support_set, targets, known) + forecast_if_killed + bell_redirected; walk cache with
  widening; fine / window / bbox placements; family walk templates for later instances; idle body, collider, hazard
  tubes; death tails; wave entries; waiting wave members bounded by their wave's earliest activation (no collider
  tube before it); dead Tinies walked only while a Maestro is in play; Tiny groups by 4 u grid cell;
  `boss=Forecaster` wraps Bell Beast bit for bit (a proxy since the fix round). `combat/forecast.py`: the
  boss-independent walk / place helpers
  (entry_grid, active_within, exit_interval, placement_occupancy) moved out, Bell Beast unchanged.
- `combat/projectiles.py`: deterministic paths (bell physics incl. the Nail Hit redirect and the dome tube, javelins,
  bomb rows with 9-10 frame steps from the latest step seen, rune slams) and the physics clock. `combat/wave_tracker.py`
  (BattleScene rules from what the view sees; room.battles only as test truth).
- Tools: `multi_recall` (dev / fresh / bellbeast; oracle and ve), `projectile_audit`, `consistency_audit` (new),
  `planner_bench --encounter Forum --multi [--planner]`.
- Tests: `tests/test_multi_forecast.py` 20 (incl. the kill what-if, a waiting wave member, Tiny groups, forecasters
  sharing tables, bomb rows from a recorded row). Full suite (at eb5d221-ish): 1052 passed, 1 skipped, 1 xfailed;
  `test_hitbox_tables.py::test_support_query_budget_on_the_committed_bell_beast_templates` failed only on time (p99
  3.54 ms vs 3 ms) with the machine at ~97 % CPU (my recall runs + 5 game instances); rerun it on a quiet machine.

### Measurements (acceptance)

All on 5332426 (frozen checkouts, below-normal priority, NUMBA_NUM_THREADS 2 per worker) unless noted.

- (a) Bell Beast wrapped: `multi_recall bellbeast` on 20261003_144536 i4_000, 4001 frames (eb5d221; later commits do
  not touch the boss path): 0 differences in placements, occupied, prob, support_set, committed, tactics, planner
  decision; the fixture-window bit-identity test and the Bell Beast tests pass on 5332426.
- (b) Recall through MultiForecast (contact at c vs forecast at c - L), union and own-type: dev (R0's 107 fights,
  3-way) 228,333 / 228,333 at L2, L3, L4; fresh R0 35 fights 74,120 / 74,120 with each fold's tables; R1 187 fights
  (w2 ghosts excluded) 112,949 / 112,949 with each fold's tables; ve (35 fresh fights, placeholder phase table,
  fold-0 tables) 74,120 / 74,120. Every one of the 9 types 100 % in every group and lag, own-type too.
  `C:\ssbot\data\m2_forum_r2\recall_{dev,fresh,ve}_5332426.json`.
- (c) Projectile path centre error (`projectile_audit`, 10 R0 caches, 0.8 s): bell p99 0.246 u (0.0005 at 0.1 s, 0.20
  at 0.4 s; max 7.5), javelin p99 0.050 u, bomb rows x p99 0.025 u with 2020 / 2098 predicted bombs lit inside their
  window (the rest: sides the bomb pool served late). `proj_audit_10c.json`.
- (d) Wave-6 replay (074719 i3 ep0, 5951 ticks, 6-8 enemies): forecast(2 s) p50 0.91 ms, p99 2.75 ms (max 10.0, once);
  machine CPU p50 53 % (4 recall workers + 5 game instances). `bench_wave6_fc_5332426.json`. Did not reproduce (the
  verifier: p99 3.08 / 3.23 / 3.21 ms at the same load): superseded by the fix round below.
- (e) Memory: peak working set 1,109 MB (with the planner 1,184 MB); tables 696 MB; load 25 s, warm 55 s.
- (f) Consistency (`consistency_audit`, 35 fresh fights, every 30th frame, +-2 u near / +-6 u wide, 1 s): kills 0
  violations (172,839 simulated, 1,429 recorded what-if, 1,429 recorded before/after); bell redirects: 0 of 474
  recorded, 9 of 2,854 simulated in the near zone, all physics (a down hit bounces after Nail Hit 2, an up hit falls
  back 4, a side hit off a near wall comes back at 10 u/s 2, an up hit reaching the dome becomes a tube 1).
  `consistency_5332426.json`. Fixed on the way (forum.md 14.4): a kill gave the attack it cut short a tail; a
  wave-ending kill walked the next wave's parked members at once (with their collider tube); a store bug - a coarse
  base key registered again took the next new key's id, so the next fight in one process used other family walks'
  box tables (every multi-fight recall before 5332426 ran with it; they were 100 % anyway).
- (g) Today's planner fed by the MultiForecast (HOLD prefs, floor risk map): tick p50 21.6 ms, p99 37.9 ms (support
  6.5 / 16.5, prob_bind 6.4 / 14.7), FORCED_RISK on 92 % of the ticks; machine CPU p50 60 %.
  `bench_wave6_planner_5332426.json`.

### Fix round after verification (commits 421176d - 568d873, offline)

Two verifiers re-ran (a)-(g) on f274317 and refuted four claims; all fixed and re-measured (forum.md 14.7 has the
details, 14.2-14.5 the new numbers):

- **The Bell Beast wrap was not a drop-in**: it forwarded reads only (`det` read-only, the multi path's `_occ`
  shadowed Forecast._occ), so the live policy's `bell_hit_monitor.zone` raised on 4,965 / 4,965 calls. MultiForecast
  in boss mode is now a proxy (reads and writes of everything it does not answer go to the boss Forecast; the multi
  union query is `_union_occ`), and `MultiForecaster(boss=fc)` no longer resets `fc`. `multi_recall bellbeast` now
  also compares the zones: 0 differences in all 8 surfaces on i4_000 (4001 frames, 892 zone checks) and on
  20261004_095304 i0_001 (4001 frames, 1,333 zone checks); a test wraps a Forecaster mid-window.
- **Tiny group rows were owned by one Tiny**: `occupied_without(owner)` dropped the other Tinies of the cell
  (17,870 of 92,276 cells in the verifier's probe), `occupied_only(member)` missed the group rows. Group rows now carry
  their cluster (`bb["gcl"]`, `MultiForecast.clusters`): kept while one Tiny of the cluster is in, included for each
  of them, one support event each. `consistency_audit` now also checks `occupied_without(victim)` against the others'
  support after the kill: 0 violations.
- **Recall skipped the multi-hit chains' first contact** (the hook is not a contact row): `multi_recall` adds one hook
  contact per chain (`hook_contacts`) and counts it in n.
- **WaveTracker never resynced after a missed kill** (vision view): only members new in play activate a wave; a new
  next-wave member 2 s after the activation resyncs; VE "unknown" / "hidden" phases are not in play.
- **The bell path was not a superset on held-out data** (1,581 of 1,157,991 boxes outside): side-bounce branches
  after every floor bounce (384 of 8,813 logged floor bounces get vx +-10 on the next step) and a 1.1 u dome band
  (air contacts reach 1.01 u below the dome line).
- Lows: an old state is walked from the origin when age + H passes WALK_CAP_S; comfort requests are counted and
  documented (no comfort templates in the multi path, so (e) / (g) exclude them); the Bell Beast query budget test
  skips with its numbers on a busy machine (it failed on main too); forecast build ~15 % faster.

Measurements (frozen `C:\ssbot\live_r2fix_e516f22`, the audit on `live_r2fix_568d873`; below-normal priority;
outputs in `C:\ssbot\data\m2_forum_r2\`, driver `fix_run.cmd <mode> <rev>`):

- (a) `bellbeast_wrap_i4_000_e516f22.json`, `bellbeast_wrap_095304_i0_001_e516f22.json`: 0 differences (above).
- (b) Recall with the hooks, union and own type, 100 % at L2 / L3 / L4 for all 9 types in every group: dev 229,711 /
  229,711 (1,378 hooks); fresh R0 74,585 / 74,585 per table (465 hooks); R1 113,385 / 113,385 per table (436 hooks);
  ve 74,585 / 74,585 (465 hooks). Every Final Hit row found its hook. `recall_{dev,fresh,ve}_e516f22.json`.
- (c) Held-out (35 `cache_fresh` caches): bell p99 0.233 u (0.0005 at 0.1 s, 0.185 at 0.4 s), 3,469,352 / 3,469,352
  boxes inside the support; javelin p99 0.050 u, 108,459 / 108,459; bomb rows x p99 0.148 u, 8,093 / 8,391 lit inside
  their window. Build 10 caches: bell p99 0.229 u, 1,001,308 / 1,001,308. `proj_audit_fresh35_e516f22.json`.
- (d) Borderline: three runs p99 2.57 / 2.49 / 2.48 ms (p50 0.77 / 0.69 / 0.64 ms) at machine CPU p50 50 / 44 / 36 %;
  side by side with 5332426 at the same load 3.14 -> 2.72 and 3.05 -> 2.61 ms. The tail is machine noise (the same
  tick computed twice: min-of-two p99 2.51 ms under heavy load where the first run's p99 was 4.67 ms; no GC pass inside
  a forecast). Only ~15 % margin: a saturated machine still goes over 3 ms. `bench_wave6_fc_e516f22_{1,2,3}.json`.
- (e) Peak working set 1,109-1,112 MB (with the planner 1,187 MB), store 696 MB, load 26-29 s, warm 49-61 s; no comfort
  templates (R3 adds them: roughly double, forum_planner_plan §1 item 8).
- (f) `consistency_568d873.json`: kills 0 violations (172,839 simulated, 1,429 recorded what-if and before/after),
  occupied_without 0 violations (same checks); redirects 0 of 474 recorded, 14 of 2,854 simulated in the near zone:
  the 9 physics cases as before plus 5 made only by the side-bounce branches (real physics, modelled both ways).
- (g) Today's planner on the MultiForecast: tick p50 14.2 ms, p99 25.6 ms (CPU p50 42 %; support 4.1 / 12.0,
  prob_bind 3.7 / 9.8 ms), FORCED_RISK 92.0 % - an open-loop replay (hero positions from the data policy), not a
  closed-loop rate. `bench_wave6_planner_e516f22.json`.
- Tests: `pytest -q` (tests + ssbot/tests) 1071 passed, 2 skipped (one the budget test on the busy machine), 1 xfailed;
  `tests/test_multi_forecast.py` 25.

The person's question (2026-10-04, "bot反应会比我0.5倍速快吗？还是没打出无伤"), corrected answer: the bot's reaction time
has not been measured end to end; recall at a 2-4 frame lag says how early the forecast covers a contact, not how fast
the bot reacts. The PC budget (DESIGN §3.8.4) is p99 <= 60 ms from the game's frame to the input taking effect (P8
measured 45.6 ms Esc -> first dark frame without compute), about half the person's ~200-250 ms visual reaction at
0.5x (100-125 ms of game time) - if the budget holds. Today it does not for the Forum: the planner tick with the
MultiForecast is p50 14-22 ms, longer than a 16.7 ms frame (Bell Beast live: p99 tick 19.1 ms median, ~7 late frames
per fight). No-hit is not a reaction question yet: there is no Forum tactics / planner (R3-R6) and no live Forum run
with the MultiForecaster; the 92 % FORCED_RISK is an open-loop replay figure.

### Running

Nothing (all fix-round runs finished).

### Next

1. R3: today's planner with the MultiForecast spends p50 ~12-22 ms in its phases (support, prob_bind) and is in
   FORCED_RISK 92 % of the wave-6 ticks (open loop, no Forum tactics); the Forum vocabulary, K-target scoring and the
   support query budget are R3's. Before R3 adds per-tick work, regain (d) margin: move `groups()`'s piece / anchor-box
   math into numba, give a dead Tiny walked for a summon its arena box without the piece machinery.
2. The physics clock is not narrowed for the first bell of a fight (p99 0.67 u on 0.2 % of the samples): narrow it from
   any Rigidbody the export has (the hero) or keep the phase across fights of a session.
3. A bell landing on a resting bell (one case in 142 caches) is not modelled; the side-bounce branches are one level
   (a branch's own later floor bounces do not branch again).
4. VE recall used the placeholder phase table (identity) and the tables' body offsets; rerun with the real vision
   phase tables when they exist; the WaveTracker resync assumes the vision view's iids are stable.
5. Comfort templates for the multi path (R3), then re-measure (e).
6. Frozen checkouts to remove (their runs are done): `C:\ssbot\live_r2scan_56845a9`, `live_r2recall_abca5c9`,
   `live_r2recall_948f32c`, `live_r2final_69e9b36`, `live_r2final_9835ced`, `live_r2final_21d697f`,
   `live_r2final_5332426`, `live_r2fix_e516f22`, `live_r2fix_568d873` (git worktree remove).
7. Wiring the MultiForecaster into the live loop is not done (R2 is offline): one forecaster per episode on shared
   tables is safe (the store fix), `warm()` belongs before the fight; `MultiForecaster(boss=fc)` may wrap a Forecaster
   that already has state.

## Task R3 - Forum plan round R3: the fast layer (branch worktree-wf_449c2ee3-df3-1)

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_449c2ee3-df3-1` (from main fe50ef9). Offline, plus the Bell
Beast mini batch on instance 3. Facts: `docs/facts/1.0.30000/forum.md` section 15 (Chinese). Outputs (not in git):
`C:\ssbot\data\m2_forum_r3\` (drivers `cert.cmd`, `kin.cmd`, `bench.cmd`, `bb_batch.cmd`, `bb_identity.cmd`,
`scan3.cmd`; results `recall_*`, `kin_*`, `bench_*`, `bbdec_*`). Frozen checkouts (git archive, no .git: behaviour_build
needs `--allow-no-sha`): `C:\ssbot\live_r3_2a10a0d` (certification), `live_r3kin_d9dd529` (Bell Beast batch, scans),
`live_r3_0d735f4` (kin_check final, benches load1), `live_r3_2b8f5c7` (final benches), `live_main_fe50ef9` (Bell Beast
identity baseline), `live_r3cert_5d0243b` (superseded).

### Done (committed)

- Certification fix (forum.md 15.1): the 13.13 miss is covered by the MultiForecast already (window / bbox rows; 2 u
  of margin), it was SubjectRecall's; the structure behind it (CM_SLASH anchored at Fly To Slash, 3.3 u from where the
  Clawmaiden struck) is fixed by re-anchoring: an instance entering another start state of its family is also placed
  as an instance from that state, anchored where the enemy is then (EnemyTracker Instance.re_*, MultiForecast).
- Forecast tightenings found by the wave-6 diagnosis (forum.md 15.2): the walk's lower bound (a zero-dwell loop drove
  entries to -333 s; every Tiny's later instances were arena-wide boxes over the whole horizon; recall forecasts 2.4 ->
  0.7 ms), arena boxes from the templates' boxed bins and merged per window, dead / parked Tinies back no earlier than
  a Maestro's Summon (105 of 105 revivals on the Summon frame).
- ForumPlanner (`combat/forum_planner.py`, forum.md 15.3): posture families + the 56-row core evasion set
  (`candidates.build_forum`), stage 1 nominal + centre support on frames 1-3 and every other one, stage 2 bounds_lo
  envelope in 32-row chunks with K_b 96, V siblings and the 11 ms deadline (core rows always enveloped; no safe row ->
  checks on), Reaper shapes over the 4 nearest targets with GoalPrefs.hit_w, hit branches (32 / tick) with the hit
  enemy's reaction (hero_caused TOOK DAMAGE exits, MultiForecaster.forecast_reaction, 4 / tick), dash-stab rows vetoed,
  FORCED_RISK ranked by time in contact (exact_p optional), EnvelopeAudit; U = the blow that may end the battle
  (`forum_kill_hp`, I3 only: no kill branches), YELLOW per-enemy kill freeze (`forum_yellow_kill_hp`,
  `kill_freeze_s`); `GoalPrefs`; `planner_bench --forum`.
- Supervisor: `forum_supervisor_config(weighted)`: worst_known_damage 2, Q4 per enemy instance (2) or 3 in all
  (`SupervisorInput.unpredicted_sources`), post-hit window 1.3 s with the Weighted Anklet; Bell Beast defaults unchanged.
- Kinematics (Forum loadout only, forum.md 15.6): landing resets a swing whose slash is over (BackOnGround ->
  ResetAttacks); a ground dash ending at a wall ends the sprint (Dash To Run); Sprint Grace on the ground sprint only,
  0.2583 s (the estimator restarts the timer on landing too).
- Tests: `tests/test_forum_planner.py` (14: §4.4 items 2 and 3 as property tests, vocabulary, posture, hit reaction,
  kill rules, Q4 per instance, the anklet window, Reaper shapes), `tests/test_multi_forecast.py` +2 (re-anchoring, walk
  floor). Full suite: 1098 passed, 2 skipped, 1 xfailed (at 0d735f4-ish).

### Measured (acceptance; forum.md 15.5-15.8)

- (a) §4.4 items 2 and 3 as property tests (`tests/test_forum_planner.py`): the core rows' S / Hz / U bit-identical
  under 8 random GoalPrefs in 4 positions (deadline 0 / 50 ms), goal FORCED_RISK => default FORCED_RISK; the chosen
  S = 0 plan enveloped in every tick at deadline 0 / 2 / 50 ms. Audit on the benches (9,003 ticks): chosen S = 0
  1,173 = enveloped 1,173, core_not_enveloped 0, overrun 0.
- (b) Bell Beast: decisions of main fe50ef9 vs R3 (0d735f4) on 20261003_144536 i4_000 and 20261004_095304 i0_001,
  4,001 ticks each: 0 differences (index, name, S, FORCED_RISK, mask, J, P, plan and path hashes;
  `bb_identity.cmd`). 50-episode oracle batch on instance 3 (`live_r3kin_d9dd529`, seeds 139100+,
  `20261005_013127_BellBeast_eval_planner_oracle`): 50 / 50 CLEAR, 0 WOULD_DIE, 0 unpredicted hits, plan p99 median
  15.3 ms. (A first try, seeds 139000, `20261005_012618`, stopped after 3 episodes: "paused unasked" -> time scale 0;
  2 CLEAR + 1 HARNESS_FAIL, not counted.)
- (c) Forum open-loop bench (074719 i3 ep0, 3000 frames each, CPU p50 42-58 %, `bench.cmd live_r3_2b8f5c7 final`):
  tick p50 / p99 after: wave 6 (Maestro x2) 8.06 / 18.19 ms, wave 11 (mixed) 6.13 / 16.90, wave 13 (finale) 6.31 /
  14.52; Bell Beast under the same load 5.71 / 18.20 and 5.93 / 18.44 (before / after the Forum runs); before (today's
  planner, R2 checkout) 19.2 / 31.0, 14.2 / 24.6, 15.3 / 23.9. FORCED_RISK before -> after: 90.8 -> 85.9 %, 88.0 ->
  84.4 %, 93.7 -> 91.6 % (open loop: the data policy's hero is in support within frames 1-3 on 99.9 % of the forced
  ticks). Wave 6's p99 equals the Bell Beast's (18.19 vs 18.20 / 18.44): no margin. At CPU 72-86 % (`load1`) wave 6's
  p50 was 11.6 ms (Bell Beast 7.5).
- (d) Recertification through MultiForecast on 2a10a0d (R0's tables and margins; L2 / L3 / L4, union and own, hooks
  counted): dev 107 fights 229,711 / 229,711; fresh 352 fights (R0's 35, R1's 187, 13.13's 130 1x incl. the missed
  fight) 304,072 / 304,072 per table; new 357 fights nobody had seen (162411 ep60+, 195019, 195800; all 1x) 180,145 /
  180,145 per table. Every type 100 %. known = True; recorded in `support_margins.json` `runtime_certification`.
- kin_check (Forum loadout, bounds_lo_mix, `kin.cmd`): held-out dash 97.34 -> 99.67 % (3,048 windows), held-out all
  99.262 -> 99.404 %, fit + dev unchanged (dash 100 %, all 99.064 %); no other category moved.
- Tests: full suite 1098 passed, 2 skipped, 1 xfailed.

### Fixer round (after the review; commits 9a8b05d .. HEAD; forum.md 15.11)

- Refuted (c) p99: the p99 ticks were all ticks with a safe row where the envelope ran to the 11 ms deadline. Now
  deadline 8 ms with a predictive stop (no chunk that would end past it, taken to cost what the last one did; the
  core rows still always enveloped), the hit branch's reaction contacts one query per reaction (was one per row,
  ~0.37 ms each), and MultiForecast's support query builds and tests all five box kinds at once (was one array build
  and kernel call per kind, ~0.45 ms per query; bit-identical union, test). Re-measured interleaved
  (`C:\ssbot\data\m2_forum_r3fix\bench_fix.cmd live_r3fix_1e45c67 fix2`, CPU p50 29-31 %): wave 6 tick p50 / p99
  6.04 / 13.49 and 5.84 / 13.51 ms, wave 11 4.30 / 11.25, wave 13 4.96 / 10.88; Bell Beast 15.12 / 15.37 / 13.88 (p99,
  before / between / after). Margin 0.4 ms to the lowest Bell Beast run; not re-measured at high load.
- FORCED_RISK ranking: the hit branch's contact joins the row (t_hit, contact frames; a capped row in contact from
  its hit frame); the p_k candidates are compared on one lane and one frame set (nominal, stage 1's frames; stage 1's
  first contact is a lower bound now).
- Hit reactions: from every state the walk allows at the hit (`reaction_states`, `_WalkCache.states`), one forecast
  for all, anchored at the hit time (dead reckoning + idle growth + view spread, both mirrors; the re-anchor path of a
  same-family reaction is placed too, it was not before). The real forecast is bit-identical (certification stands).
- Caps never decide FORCED_RISK: without a safe row the capped rows get their hit branch uncapped first (audit
  `uncapped_ticks` / `uncapped_rows`; property test with hitfx_k 1, react_k 0). The first hit is looked for on every
  enemy within 14 u (the 4 nearest scored). `ForumConfig.deadline_ms = inf` = deterministic decisions
  (`planner_bench --deadline-ms`); `planner_bench --ticks-json` writes per-tick records.
- Template files: sha256 in `support_margins.json` `runtime_certification.table_files`; canonical copy
  `C:\ssbot\tables\forum_r3_2a10a0d` (copy into `knowledge/1.0.30000/enemies/forum/` of a new checkout).
- kin_check: T1 + T2 relabelled a development set (forum.md 15.6). Untouched excitation recordings have 1 dash window;
  on an untouched Forum combat recording (195019 i0_000, 131,328 windows) planner_bounds dash is 78.45 % (4,259), the
  same as before R3's kinematics (2a10a0d): the plan's "dash >= 99 %" is far from met on live Forum data, cause not
  investigated.
- Tests: full suite 1107 passed, 2 skipped, 1 xfailed (tests + ssbot/tests); `tests/test_forum_planner.py` 22 items.
- Frozen checkouts added: `C:\ssbot\live_r3fix_9a8b05d` (base bench), `live_r3fix_762d90f` (fix1),
  `live_r3fix_1e45c67` (fix2, kin_check); outputs `C:\ssbot\data\m2_forum_r3fix\`.

### Running

- Instance 3: the 1x Forum wave-start collection restarted after the batch, `C:\ssbot\sandbox\r3_collect_i3.cmd`
  (the r1c_collect i3 command from the fixed frozen code `C:\ssbot\live_r1cfix_ed65873`, seeds 140000+, 9 h from
  02:28): run dir `C:\ssbot\data\runs\m2\20261005_022858_Forum_A_w2_mix_data2`, log `C:\ssbot\sandbox\r3_collect_i3.log`.
  Stop: `cd C:\ssbot\live_r1cfix_ed65873\brain; ..\scripts\uv.cmd run python -m ssbot.tools.combat_run stop <run dir>`.
- Instances 0 and 1: their collection runs (195019, 195800) ended on their timeboxes at 01:50 / 01:58 (not restarted
  here); instance 2's 233950 runs to about 07:39; instance 4 untouched.
- Offline: nothing.

### Needs deploy

- Nothing (no oracle change).

### Next

1. R4: wire the fast layer into the live loop (MultiForecaster per episode on shared tables, ForumPlanner with the
   Forum params and `with_weighted()` when `ws.res.equipped` has the Weighted Anklet, `forum_supervisor_config`,
   `SupervisorInput.unpredicted_sources`, FilterContext.kill_hp = `forum_kill_hp`, kill_prims from
   `forum_yellow_kill_hp`), then the A0 baseline.
2. The hit-branch cap (32 / tick) left 1,464 attack rows of wave 11 at S = 1: order the hit branches by J across
   chunks, or raise the cap with the margin the bench leaves (wave 11 p50 6.1 ms).
3. Wave 6's p99 has no margin over the Bell Beast's: the stage-1 support query (1.4 ms p50, 3.5 p99) and the rollout
   (1.8 / 3.6) are the next to cut (fuse rollout and support, §4.5).
4. The killing blow's branches for the final kill (certified kill instead of I3 only); comfort templates for the
   multi path; the lock check past the horizon if Silkspear comes back into the Forum set.
5. bounds_lo vs bounds_lo_mix for the envelope (kin_check validates the latter).
6. Sprint Grace 0.2583 s is fitted (template 0.3 s): read the hornet_sprint Sprint Timer actions; check the landing
   reset (ResetAttacks) on live Forum recordings (no excitation window isolates it).
7. A recording with the Weighted Anklet equipped to check `with_weighted()` and the 1.3 s post-hit window.
8. Frozen checkouts to remove when done: `C:\ssbot\live_r3cert_5d0243b`, `live_r3_2a10a0d`, `live_r3kin_d9dd529`,
   `live_r3_0d735f4`, `live_r3_2b8f5c7`, `live_main_fe50ef9` (plain directories, not git worktrees).

## Task R4 - Forum plan round R4: the A0 baseline (branch worktree-wf_89d18409-0b6-1)

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_89d18409-0b6-1` (from main 9dddedf). Facts: forum.md section 16
(Chinese). Frozen checkout `C:\ssbot\live_r4_c86b48e` (git archive of c86b48e + the R3 tables from
`C:\ssbot\tables\forum_r3_2a10a0d`); outputs `C:\ssbot\data\m2_forum_r4\`; driver `C:\ssbot\sandbox\r4_a0.ps1`
(log `r4_a0.log`).

### Done (committed)

- `train/forum_planner_policy.py` ForumPlannerPolicy (combat_run `--policy planner` on a gauntlet encounter): the R3
  fast layer live (ForumPlanner over a MultiForecaster on the production tables, the Forum loadout's kinematics,
  `with_weighted()` and the 1.3 s post-hit window when `ws.res.equipped` shows the Weighted Anklet - fo_A has none),
  `forum_supervisor_config` with `unpredicted_sources` (HIT_TAKEN source iids), kill_prims from `forum_yellow_kill_hp`,
  `FilterContext.kill_hp = forum_kill_hp`; Cogfly throws (Up + QuickCast, 2 frames) gated on the support's t_min;
  per-wave accounting; the WaveTracker checked against room.battles on every ticked frame (test truth only).
  The Bell Beast's PlannerPolicy is untouched (bit-identical by construction: no shared code changed except
  `WaveTracker.current`, which the boss path never calls).
- Multi-hit chains: a chain's Final Hit (the hero's "Roar and Wound States" FSM, DamageHeroDirectly) is judged at the
  chain's hook as in R2's recall (`_hook_of`); judged at its own frame it was counted unpredicted (replay 154609 i0 ep0:
  Choristor Whip Hit 2 Final Hit 20 frames after the hook).
- `combat/tactics/forum_local.py` ForumTactics (LOCAL: HEAL Q1a / Q6, LEAVE (pocket rule 2), EVADE, ENGAGE with
  Clawmaiden first and distant Bellbearer / Maestro last, defensive stances hit weight -1, HOLD), `Forum.yaml` v0.
- `WaveTracker.current(t)`: the wave BattleScene runs (switches at the rule's activation time); `wave` / `t_active`
  (the forecast's) unchanged.
- Tools: `forum_policy_replay` (open-loop replay, also warms the numba caches), `forum_a0_report` (6.3 metrics).
- Tests: `tests/test_forum_tactics.py` (5); test_forum_planner + test_multi_forecast + tactics 54 passed.

- Fixes found live / in the replay: `MultiForecast.known` (ffe0e82: an enemy whose Control FSM never ran is parked, not
  unknown; wave index 1's Choristors have their Attack FSM disabled until activation, so the first live try
  `20261005_044825` (22 episodes, void) had known = False on every wave-0 tick and Q3 quit at once); a wave-start
  savestate starts the WaveTracker at its wave (b063cae).

### Measured (forum.md 16.2-16.3; reports `C:\ssbot\data\m2_forum_r4\a0_report.json`, `ws_report.json`)

- A0, 52 full gauntlets from fo_A (`20261005_045446_Forum_A_eval_planner_oracle`, `live_r4_ffe0e82`, seeds 150000+,
  eval, oracle, real quits 0.2): QUIT 52 / 52, all Q3 (h = 2 with a multi-hit event in the support: Reed 49,
  Choristor 3), all in wave 0, p50 10.1 s after the battle start; 2.42 hits per episode = 126 damage events (Envoy 49,
  Reed 40 = body 24 + Pin Projectile 16, Choristor 37; fixer round, per damage event with the caller path) plus 30
  Multihit ticks (special_damage, no source; the first report's "Envoy 49, Choristor 37, Reed 24, unresolved 46"
  counted the 156 HIT_TAKEN); **0 hits outside the support** (24 chain Final Hits judged at their hook; 7 of the 30
  ticks had no Final Hit and were not judged live, the verifier's offline replay found all 156 inside);
  FORCED_RISK 86.6 % of the ticks (17.5 streaks / min), EVADE 100 %; chosen S = 0 plans 3,629 = enveloped 3,629; tick
  p50 / p99 medians 7.4 / 15.4 ms (max 21.6), 1.0 % of ticks > 16.7 ms; real quits 13 / 13 to the main menu, 0 wrong
  submits; 1 kill in 52 episodes. WaveTracker vs room.battles: live 28,170 / 28,170 frames (wave 0 only); offline full
  gauntlet replay (154609 i0 ep0, 14 waves) 43,900 / 43,917 (99.96 %: the replay's first frame, wave 3 three frames
  and wave 5 thirteen frames early).
- A0 from the 12 wave starts (`20261005_050427_Forum_A_w2_mix_eval_planner_oracle`, instances 0 / 1, 24 episodes):
  QUIT 24 / 24 (Q3 14, Q1 10), 3.04 hits per episode (72 damage events seen by the policy + 11 Multihit ticks; per
  true wave 3:12 4:2 5:7 6:12 7:6 8:5 9:3 10:8 11:4 12:6 13:7), FORCED_RISK 65-100 % per wave (wave 2 100 % over 149
  ticks, wave 13 65.3 %; the first report's 69-95 % missed both), 0 hits outside the support, sources Clawmaiden 22
  (body 15 + spear 7), Tiny 14, Clapper 13, Reed 12, Minister 4, Bellbearer 3, Choristor 2, unresolved 2;
  WaveTracker 98.6 % (the wave-start offset, below). Corrected reports: `C:\ssbot\data\m2_forum_r4\fixer\a0_report_v2.json`,
  `ws_report_v2.json`.

### Running

- Instances 2 / 3: the 1x wave-start collections, restarted by the driver at 05:00 from `C:\ssbot\live_r1cfix_ed65873`
  (seeds 162000 / 163000, 9 h): `C:\ssbot\data\runs\m2\20261005_050022_Forum_A_w2_mix_data2` (i2) and
  `20261005_050022_Forum_A_w2_mix_data2_2` (i3); logs `C:\ssbot\sandbox\r4_collect_i2.log` / `_i3.log`. Stop:
  `combat_run stop <run dir>` from that checkout's brain.
- Instances 0 / 1 idle (their collections had ended before this round); instance 4 untouched.

### Fixer round (after the verifier; commits 10adf31, 0f517a0, 95fab30 + this)

- Medium: YELLOW's per-enemy kill freeze rule (plan 4.4 item 7) did nothing with a certified support at h >= 2 (the
  supervisor left the kill to the L0 filter, whose Forum kill_hp is None before the finale). `SupervisorConfig.
  kills_certifiable` (default True: Bell Beast unchanged), False in `forum_supervisor_config`: YELLOW / RED withhold
  kill_prims whatever the support and h. Test `test_yellow_withholds_a_freezing_kill_even_when_known_at_h2`.
- Lows: HIT_TAKEN sources paired by caller path (a blocked damage event gets none); chain hooks keyed by instance
  (FSM `ent`) with an object-name fallback over every part of the source path; Multihit ticks judged at their own frame
  (outside: wait 70 frames for the chain's Final Hit, else counted; flushed at the episode end); the Cogfly's second
  frame dropped on FORCED_RISK / pause pending / supervisor keys; `forum_a0_report` counts hits per damage event
  (ticks apart, types from the caller path, old records via the recording's events.jsonl). Tests
  `tests/test_forum_policy_hits.py` (5); targeted suites 133 passed.
- Refuted claims corrected above and in forum.md 16.2 / 16.3 (hits by source per damage event; wave-start FORCED_RISK
  65-100 %).
- Re-measure (forum.md 16.5): the wave-start batch again from `C:\ssbot\live_r4f_0f517a0` (instances 0 / 1, 24
  episodes, seeds 170000+, run `20261005_054233_Forum_A_w2_mix_eval_planner_oracle`, report
  `C:\ssbot\data\m2_forum_r4\fixer\ws_report_fix.json`, driver `C:\ssbot\sandbox\r4f_ws.ps1`): QUIT 24 / 24 (Q1 12,
  Q3 12), 3.33 hits + 0.25 Multihit ticks per episode, 0 outside the support, 0 unknown (6 ticks all inside at their
  frame, 4 Final Hits with a hook), FORCED_RISK 90.5 % (69-100 % per wave), kills 0 (2 before), tick p99 median
  14.0 ms, WaveTracker 98.5 %. Full-gauntlet A0 not re-run (its numbers stand; the kill rule hardly matters while the
  bot only evades).
- Frozen checkout `C:\ssbot\live_r4f_0f517a0` can go when done.

### Needs deploy

- Nothing (no oracle change).

### Next / open issues

1. The A0 numbers are the baseline: R5 (terminal value: E / trapped / H_exp) and R6 (BAIT / FOCUS / SPLIT) must cut the
   87-95 % FORCED_RISK; the 3.0 u search-cap margins (Reed needle, Clawmaiden spear, Minister block, Tiny ram, bells,
   rune bomb) are the biggest lever but need recertification.
2. Q3 at h = 2 whenever a multi-hit event is in the support ends every attempt after ~3 hits: the person's decision
   (forum_planner_plan §9 item 2).
3. WaveTracker: the view counts a death at the killing hit, BattleScene (probably) at HealthManager.Die after the kill
   freeze (3 / 13 frames early at waves 3 / 5 in the full-gauntlet replay, unverified); on wave starts `start()` adds the
   start delay to a wake the intro already moved to the activation (10-113 frames at the episode start).
4. (Fixed in the fixer round: the report resolves types from the caller path and counts ticks apart.) Two damage
   paths stay unresolved (`Colliders/Collider ParryStance`, `Colliders/Collider Fly`, wave-start batch).
5. The Cogfly throw is not in the kinematic model (gated on t_min >= 1 s, 2 throws seen); the Weighted Anklet path
   (with_weighted, 1.3 s window) never ran (fo_A has no anklet).
6. Frozen checkouts to remove when done: `C:\ssbot\live_r4_c86b48e` (first try, void), `live_r4_ffe0e82`, `live_r4_b063cae`.

## Task route bosses - Lace 1, Last Judge, Trobbio (branch worktree-wf_b1f47269-5cc-1)

The person (2026-10-06, "全停了吧，换个boss"): the Forum has enough data; stop it and move the machines to the other route
bosses. Facts: `docs/facts/1.0.30000/route_bosses.md` (Chinese). Probe outputs: `C:\ssbot\sandbox\route_bosses\`
(`*_scout.json` hold the full Control graphs, `smoke*.log`).

### Done (committed)

- Stopped the five Forum collections (`20261006_062333_Forum_A_w2_mix_data2*`, instances 0-4) gracefully via their
  STOP files; all five ended after their current episode.
- Survey of the community savestates (route_bosses.md §1): Lace 1, Widow, Last Judge, Cogwork Dancers, Trobbio, Lace 2
  and GMS have a "Boss - <name>" savestate; Fourth Chorus has only the skip trick's. Wired: Lace 1, Last Judge,
  Trobbio. Widow needs a dialogue (Speak Region) to start, Dancers are two bosses (the single-boss builder does not
  fit), Lace 2 / GMS left for budget.
- `probes/route_bosses.py` (scout / save / graph); training savestates `rb_lace1` (vs_p6_s3 walked left to x 83.50,
  encounteredLace1 True: refight, no dialogue), `rb_lastjudge`, `rb_trobbio` (community positions).
- `train/encounters.py`: LACE_1 / LAST_JUDGE / TROBBIO (`walk_intro`, `death_on_kill` for Lace 1 whose Control has no
  death state), `<name>_low` late-phase variants (`start_boss_hp` 0.25-0.6 via the oracle's `enemy.hp`).
  `train/episode.py`: FightTap follows the episode's encounter (rotation of bosses on one worker), the kill from the
  boss's hit event when `death_on_kill`, the boss's Control matched exactly (Trobbio's bombs / tornadoes run a
  "Control" FSM under a "Trobbio ..." name), the late-phase HP cut after the start randomisation. Bell Beast / Forum
  paths unchanged (GauntletTap untouched; the exact match equals the old prefix match for "Bone Beast").
- `knowledge/behaviour_tables.py`: SPECS Lace1 / LastJudge / Trobbio (`_route_spec`: families from the FSM graphs, an
  IDLE family between attacks, INTRO family for the wake chain, `units` so a rotated run's fights are split per boss;
  `behaviour_build` filters by it).
- Oracle: RPC `enemy.hp` {type_key, hp | frac} (`oracle/src/Train/EnemyHpRpc.cs`, training profiles only), built with
  -p:Deploy=false (rebuilt in the fixer round: 0 warnings, 0 errors).
- Fixer round (3039044): FightTap's death_on_kill kill is the first dead boss hit whatever hp_before (open issue 6);
  LACE_1's cross slash starts at CrossSlash Antic, with CrossSlash Aim / CS Evade / CS Evade Cancel as decisions
  (zero-time logic states: t_in_prev 0.0 in 96 / 61 / 18 exits). Aim -> CS Evade -> Evade (43 of 61) is the ordinary
  Evade state (L1_EVADE, ctx.frm "CS Evade"); with Aim as the start half the L1_CROSS instances were aim-only stubs.
  The fixed tap, replayed on all 12 cleared Lace fights of the smoke / collection runs, gives their recorded f_kill.

### Measured (smoke, data policy, 1x, worktree code)

- Lace 1 `20261006_065722_Lace1_data` (i0): 2 / 2 CLEAR, 112.9 / 78.2 s game time, wake frames set. The first try
  (`065020`) had the savestate at the community x 89.94: the fight began before the tap's reset (no wake frame,
  void); the next (`065605`, i0) ended HARNESS_FAIL "paused unasked" 0.9 s after the wake (once; cause not found).
- Last Judge `20261006_065020_LastJudge_data` (i1): 3 / 3 CLEAR, 235.8 / 159.7 / 154.9 s; every phase reached.
- Trobbio `20261006_065020_Trobbio_data` (i4): 3 / 3 CLEAR, 233.7 / 288.5 / 244.4 s; Phase Roar every fight.
- Rotation `20261006_065605_Lace1_mix_data` (i2, Lace1,LastJudge,Trobbio): CLEAR 85.5 / 169.0 / 365.6 s.
- `behaviour_build --report-only --include-open` on the first two LJ and TR fights: scans clean (14,152 / 9,584 and
  14,024 / 17,313 frames); per fight LJ_INTRO / LJ_FLAME_ROAR / TR_INTRO / TR_PHASE about once, LJ_RAGE_ROAR 1.5,
  the rest 4-30: about 200 fights per boss for the 200-instance rule. Validation fails on a few contacts (expected
  on 2 fights; see open issues): LJ 6 uncovered (Flame Wave Dmg Full self template, Swing Attack Flame in Spin End /
  Stunned) + 25 outside attacks (Roar Glow/Damager, not exported); TR 16 uncovered (dazzle flash Damager self
  template) + 41 unexplained + 6 outside.
- Tests: `tests/test_route_bosses.py` 5, episode / combat_run tests 25, test_behaviour_tables 27: all pass.

### Tables and held-out recall (round 2, branch worktree-wf_91bca580-b72-1, offline; facts: route_bosses.md §6)

- Built from both runs (Lace 341, LJ 337, TR 335 fights; unit filter) with `--fsm-graph graph_<name>.json`; driver =
  behaviour_build's flow plus a builder pickle (scratchpad `rb_build.py`), frozen checkouts `C:\ssbot\live_bb_<rev>`,
  outputs `C:\ssbot\data\route_bosses\b0..b4` (b1 Lace final, b2 LJ final 4 shards, b4 TR final 4 shards; the
  pickles are 0.6-9.4 GB each and can be deleted). The full LJ / TR table phase is slow (TR 6,432 s; LJ ~20 s per
  fight scan), so the final LJ / TR builds are 4 shards (every 4th fight): counts add up, the held-out folds inside a
  shard train on ~42 fights (stricter than the full build: TR_PHASE 97.4 % full vs 89.4 % sharded, same code).
- Held-out recall = the builder's own 2-fold held-out (folds by recording = whole fights): held-out anchor contacts
  within the full build's support radius (+-4 bins). The Bell Beast way (support_recall with the Forecaster, L 2-4)
  needs a BossSpec / Forecaster for these bosses (not wired).
- Counts: every family of all three >= 200 except *_SING (0: Needolin). Lace 1: validation ok, support conservative,
  held-out anchor 100 % except L1_JSLASH 4,133 / 4,141 and L1_STUN 1,121 / 1,128. LJ: 588 uncovered pairs (447 distinct contacts), 1,398 outside
  (censer sphere), held-out 100 % except THROW 2, CHARGE 52, STOMP 19, STUN 132 misses. TR: 792 uncovered pairs (618 distinct) (Blast/Damager self templates,
  the lingering dazzle flash in TR_EXIT), 0 unexplained, 0 outside (before: 2,148 / 8,697 / 2,174); held-out, final code full build
  b5 (edcbd36, ~167 fights per fold): >= 99.4 % in every family but TR_EVADE 235 / 262 (89.7 %) and TR_PHASE
  1,291 / 1,326 (97.4 %); the b26cf2c shards (~42 per fold) give EVADE 80.2 %, PHASE 89.4 %, FLURRY 97.4 %, STUN
  97.3 %, EXIT 98.8 % (fold size). An earlier quote of the full numbers came from b0 (pre-fix code); b5 equals it but
  INTRO / FLASH (n 2,993 / 15,229, all recalled).
  LJ_INTRO / LJ_DASH / L1_INTRO have no held-out contacts: unmeasured, not 100 %. Strict recall (the planner's +-1 bin
  pairing, no +-4 bin slack) is lower: L1_CROSS 682 / 968 (70.5 %: timing jitter), TR_PHASE 94.9 %, TR_EVADE 84.7 % (full b5)
  (route_bosses.md 6.1). TR_EVADE / TR_PHASE look data-limited: ~2-3x the Trobbio fights (350-700 more), or Trobbio_low after the enemy.hp deploy.
- Fixes (36f99ef, 979cc57, 3a4e90b, b26cf2c): `direct_damage_states` (Lace's DamageHeroDirectly multi-hit: 173
  uncovered -> follow-ups), `boss_parts` (LJ "Roar Glow", TR "Trobbio_dazzle_flash": the boss's own exported
  "Damager" circle named without the boss; a part counts as the boss's while the boss exports its collider),
  `LACE_1.arena_x` (80, 115) -> (82.0, 106.0) measured (lava pits beyond), `TROBBIO.timebox_s` 420 -> 540 (the two
  STUCK were ordinary slow fights: CLEAR p99 392 s, max 415 s; attack rates as in CLEAR fights, Phase Roar reached).
- Tests: test_route_bosses + test_behaviour_tables 33 passed.
- Review fixes (edcbd36): `boss_parts` are (part root, "name:kind" of the boss collider) pairs - the bare name
  "Damager" also matched TR poly11 / poly7 and LJ poly6, so a part contact went to the boss while it exported a
  different Damager; `direct_damage_states` follow-ups only when the source is the boss GameObject itself (all 543
  Lace follow-ups were "Boss Scene/Lace Boss1": same set), the validation JSON splits follow-ups by export.
  Rebuilt with the final code (b5): Lace identical to b1 (all 543 follow-ups are the boss itself and all count as
  exported - her body box is named Lace Boss1 - so 'non-exported only' would have brought the 173 uncovered back),
  LJ shards identical to b2, Trobbio full: family n as the b26cf2c shards, 700 uncovered pairs (597 distinct) / 0 /
  0. The name + shape narrowing changed no attribution in this data. route_bosses.md 6.1 / 6.5.

### Running

- Ended 00:55 (started 23:20 hidden, below normal, frozen checkout `C:\ssbot\live_bb_edcbd36`): builds into
  `C:\ssbot\data\route_bosses\b5` - Lace1 full, LastJudge 4 shards (s0-s3), **Trobbio full** (~2 h: the final-code
  full held-out recall that replaces the pre-fix b0 numbers). Logs `b5_<boss>[_s<k>].log`; done when a log has
  "wrote". Summarise: `python <scratchpad>\rb_summary.py C:/ssbot/data/route_bosses/b5 Trobbio` (shards:
  comma-separated dirs). Script copies: `rb_build.py` / `rb_build.cmd` / `rb_summary.py` in the session scratchpad.

- None of this round's jobs (the builds ended; the single-process LJ build `b0` died at 271 / 337 when the session's
  wrapper task hit its 2 h limit - superseded by the shards).
- Ended 17:30: `C:\ssbot\data\runs\m2\20261006_072930_Lace1_mix_data`: instances 0-4, Lace1,LastJudge,Trobbio rotated per
  episode, data policy, 1x, 10 h from 07:29 (ends ~17:29; seeds 10,000,000+), frozen checkout
  `C:\ssbot\live_rb_3039044` (git archive of 3039044 + a `CODE_REV` file: code_rev "3039044" in every row). Log
  `C:\ssbot\sandbox\rb_collect2.log`. Measured cycle (first run's 32 episodes, missed kills taken out): Lace 84 s,
  LJ 167 s, TR 309 s wall per fight + ~17 s between episodes = ~10 min per three-boss cycle per instance, so ~290
  fights per boss in 10 h (the rare families come about once per fight: just over the 200 rule).
  Stop: `cd C:\ssbot\live_rb_3039044\brain; ..\scripts\uv.cmd run python -m ssbot.tools.combat_run stop <run dir>`.
- Ended (stopped 07:25 for the fixes below): `20261006_070641_Lace1_mix_data` (frozen checkout
  `C:\ssbot\live_rb_242ed28` = 242ed28, code_rev null), 32 episodes, all CLEAR after the relabel: its 3 Lace STUCK
  records (i2 ep0, i3 ep0, i3 ep3) were missed lava kills, rewritten offline with the fixed tap (outcome CLEAR,
  f_kill = the first dead hit, `outcome_orig` / `reason_orig` kept; the originals in `attempts_i2/3.jsonl.orig`).
  Its frames are good data and belong in the build together with the new run.

### Needs deploy

- `enemy.hp` (oracle). Until it is deployed the `*_low` encounters end HARNESS_FAIL (enemy.hp unknown).

### Next / open issues

1. (Done, round 2) Tables + held-out recall: see above and route_bosses.md §6. Verdict: no more data under the data
   policy (every family >= 200 but *_SING); Lace 1 can stop (validation ok, 15 held-out misses in JSLASH / STUN, none
   in the 0.5 u sense for STUN); LJ / TR gaps are structural (export / attribution), more fights do not close them.
   The Forecaster-level recall (support_recall L 2-4) needs a BossSpec / Forecaster for these bosses.
2. Validation gaps left: LJ "censer sphere/hero_damager" (1,398 contacts outside every attack: not in the export at
   all, the boss exports only its Censer Slam circle then -> oracle export change); LJ 588 uncovered (Stun Air /
   Stun Start body contacts at the stun's first frames: the body is dealt 0 in the stun, the contact is the previous
   attack's; Swing Attack Flame/Hit Circle in Stunned; Flame Wave(Clone) Dmg 5/6/7 self templates with infinite
   residual). Trobbio 792 uncovered: Blast/Damager (bomb blasts) self templates with
   infinite residual in BC Attack and the idle tail; the lingering dazzle flash (after Flash Burst exported as an entity of its
   own or not at all) in TR_EXIT and others.
3. The *_SING families need the Needolin (the data policy never sings): absent under this policy.
4. Not wired: Widow (dialogue start via the Speak Region; the person, 2026-10-06: "黑寡妇可以直接挑衅" - she can be
   started directly by taunting, no dialogue needed; "灵丝奶奶不知道" - unknown for Grand Mother Silk), Cogwork
   Dancers (two bosses: needs the gauntlet builder or a
   two-boss spec), Fourth Chorus (no savestate: walk from the skip trick's), Lace 2, GMS. The community savestates
   carry 5 masks; our route plans 7 by Trobbio.
5. After deploying enemy.hp: smoke `Lace1_low,LastJudge_low,Trobbio_low` and add them to the rotation if the late
   phases lag.
6. (Fixed, fixer round) The Lace 1 STUCK episodes were missed kills, not a hang in the lava teleport: LAVA DAMAGE
   takes HP through SubtractHP (no hit event) and can leave it <= 0 (i2 ep0: 10 -> -30); she runs Lava Hop -> Tele
   -> Lava End -> Idle -> ComboSlash and the next slash, a dead hit with hp_before -30, starts BossDeathSlow. FightTap
   required hp_before > 0 for the death_on_kill kill; it now takes the first dead boss hit (3039044). The timebox is
   not the issue; L1_LAVA stays its own family (a motion of its own).
7. Run provenance: smoke runs 065020 / 065605 recorded code_rev f20471d (main) although they ran uncommitted worktree
   code (065020's Trobbio rows still have the old prefix match: Fling / Air / Explode in attacks). `git_rev` now
   appends "+dirty" when brain/ has uncommitted changes and reads `CODE_REV` in a frozen checkout without .git.

### Round 2 - Widow, Grand Mother Silk (branch worktree-wf_91bca580-b72-2, 2026-10-06 evening)

The person (2026-10-06): the Widow fight starts by the taunt, no dialogue (round 1's "needs the Speak Region dialogue"
was wrong). Facts: `route_bosses.md` sections 1 (status), 7 (Widow), 8 (GMS), 9 (Lace 2).

Done (commits 7ac8e36, e448e7b):
- Taunt start, measured: the "Challenge Region" ("Challenge" FSM) takes the taunt (ACTION bit "taunt", the game's
  HeroActions.Taunt) as SPECIAL CHALLENGE while the hero stands in it. Widow: Boss Scene Speak Ready -> Spinner Tele
  Out -> Battle Start, Spinner Boss Control Dormant -> Set Intro Pos 2.85 s after the taunt. GMS needs it too:
  CHALLENGE START -> Intro Sequence "First Challenge" (~11 s cinematic) -> Silk Boss Control Ready -> ... -> Begin ->
  Attack Control Dormant -> Init Pause (the wake). Both community saves stand inside the region at the load.
- `encounters.py`: `taunt_intro` (taunt 6 frames, no input until the boss wakes), WIDOW (`rb_widow` = vs_p6_s7,
  "Spinner Boss", death Death Stagger; Death Stagger F is the fake death into P3), GRAND_MOTHER_SILK (`GMS`, `rb_gms`
  = vs_p7_s5, control_fsm "Attack Control", new `Encounter.phase_fsm` = "Phase Control" whose Death Hit is the kill;
  phase changes add HP, so no death_on_kill). Both in ROUTE_BOSSES (and `_low`, which needs enemy.hp; meaningless for
  GMS whose phases add HP).
- `episode.FightTap`: the kill also from the encounter's phase_fsm entering a death state. `behaviour_tables`:
  `BehaviourSpec.phase_fsm` (phase marks and the death from that FSM), SPECS Widow (WI_*, 17 families + IDLE) and GMS
  (GM_*, 12 families + IDLE, from Attack Control; her movement in Control is not a family). Graphs for the builder:
  `C:\ssbot\sandbox\route_bosses\graph_Widow.json` (Control), `graph_GMS.json` (Attack Control), `graph_GMS_phase.json`.
- Tests: `tests/test_route_bosses.py` 9 (3 new) + test_behaviour_tables 27: 36 pass.
- Collection check: the first 5 episodes (Widow, i0-i4) CLEAR in 236.7-259.7 s game, code_rev e448e7b in every row.
- Fixer round 2 (after the verifier): GMS's 621 outside-attack contacts were the dash slash (boss_parts, 0c73ba7,
  builder only: the running collection's recordings are unaffected and it keeps running); the Widow validation
  figures below are now the 4-fight ones, and both bosses' validation is FAILED, not clean. Tests 37 pass.

Measured (smoke, data policy, 1x, worktree code 7ac8e36):
- Widow `20261006_202750_Widow_data` (i0, i1): 4 / 4 CLEAR, 289.6 / 244.0 / 236.7 / 317.8 s game; wake frames, P1-P3
  and the fake death every fight. Report-only build of all 4 fights (fixer re-run): every fight scans (17,376 /
  14,642 / 14,204 / 19,068 frames), but **validation FAILED**: 3,416 contacts, uncovered 4 (3 arena "Spike Collider"
  blocked frames, set1 / set4, at t ~4.05 s in a WI_CHARGE `_tail`, residual inf: past the end of the self template's
  armed stretch; 1 blade/hero_damager in a WI_IDLE `_tail`, 0.70 u), unexplained 0, outside 0. (The 1,714 / 2 first
  reported were a 2-fight scan.) Counters: 244 boss damage-collider frames during Death Stagger (after the kill), 1
  Spinner AtkBell armed outside attacks. Rare families once per fight (WI_INTRO, WI_FAKE_DEATH, WI_RAGE).
- GMS `20261006_202750_GMS_data` (i2-i4): 3 / 3 CLEAR, 519.2 / 596.2 / 510.9 s game (timebox 720 s); all six phases
  every fight. Report-only build: every fight scans; GM_ROAR 2 per fight, GM_STOP 7; GM_CLAW, GM_HAND_DASH, GM_SING
  0. Validation 3,879 contacts, **FAILED**: uncovered 1 (Sprites/Sprite type 2 in GM_STOMP_SWIPE, residual inf),
  unexplained 39 (GM_CATCH's Slash End: DamageHeroDirectly, no collider), outside attacks 621 at e448e7b -> **0 after
  the fixer's 0c73ba7**: all 621 were the dash slash ("DashSlash Effect/SlashHit 1-5", "DashSlash End Effect/SlashHit
  1"), whose polys the oracle exports on the Silk Boss entity but whose hit source path does not pass through it, so
  no entity matched; `BehaviourSpec.boss_parts` maps those roots to the boss (GM_DASH now 905 contacts, residual 0).
- A real build of either boss writes nothing unless `--allow-failed-validation` (round 1's bosses fail the same way);
  judge the uncovered / unexplained by the held-out recall.

Running:
- `C:\ssbot\data\runs\m2\20261006_204303_Widow_mix_data`: instances 0-4, `Widow,Widow,GMS` rotated per episode, data
  policy, 1x, 9 h from 20:43 (ends ~05:45; seeds 20,000,000+), frozen checkout `C:\ssbot\live_rb2_e448e7b` (git archive
  of e448e7b + CODE_REV). Log `C:\ssbot\sandbox\rb2_collect.log`. Sizing: Widow ~300 s and GMS ~580 s wall per fight
  -> ~1,180 s per cycle -> ~27 cycles per instance: ~270 Widow and ~135 GMS fights (GMS's rarest seen family, ROAR,
  comes twice per fight).
  Stop: `cd C:\ssbot\live_rb2_e448e7b\brain; ..\scripts\uv.cmd run python -m ssbot.tools.combat_run stop
  C:\ssbot\data\runs\m2\20261006_204303_Widow_mix_data`.
- Queued (main session, 2026-10-07 01:00): `C:\ssbot\sandbox\rb3_after.ps1` (hidden, log `rb3_after.log`) waits for
  that run to exit, then starts `Trobbio,Trobbio,GMS` on instances 0-4 for 20 h (seeds 30,000,000+) from the frozen
  checkout `C:\ssbot\live_rb3_146876f` (main 146876f, Trobbio timebox 540 s), log `rb3_collect.log`: Trobbio
  TR_EVADE / TR_PHASE are data-limited (350-700 more fights) and GMS got only ~135 fights. It does not start if
  DEMO_SOON / STOP_AGENTS exists or workers are still running at 08:00.

Next / open issues (round 2):
1. When the run ends: `behaviour_build <run> --encounter Widow --fsm-graph ...\graph_Widow.json` and `--encounter GMS
   --fsm-graph ...\graph_GMS.json` (the unit filter splits the rotation), then held-out recall. Round 1's build of the
   Lace1 / LastJudge / Trobbio run (`20261006_072930_Lace1_mix_data` + `20261006_070641_Lace1_mix_data`) is still open
   (this round did not touch it).
2. GMS: the never-seen GM_CLAW / GM_HAND_DASH (Swipe Claw / Claw Swipe, global
   PREPARE DASH): check with the full data whether they are gated (Attack Choice's BoolTests) or just rare; the arena
   bounds (20-60, floor y 133.57) are provisional; her Control (drift / dash / juke) runs alongside the attacks.
3. Lace 2 not wired: the community save is in Cog_Dancers, the fight in Song_Tower_01 behind the melody lift
   (UnlockedMelodyLift); needs a training savestate there first (route_bosses.md section 9).
4. Widow's arena bounds (38-66, floor y 8.57) are provisional; the arena has spike hazards (Spike Collider sets).
   Kept as self templates (not world_fixed): the 3 uncovered spike contacts are a time-extent miss at the end of the
   armed stretch (held out 1,254 of 1,257 inside); a world frame would not change the time extent.
5. The route's Widow end is a scripted bind sequence (Death Stagger -> Can Bind waits for BIND): the route runner must
   press bind there; training episodes end at the kill. Her damage colliders stay armed in Death Stagger (244 frames
   in 4 smoke fights, + 1 Spinner AtkBell armed outside attacks): the runner must keep evading until the bind.
