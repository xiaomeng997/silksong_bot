# HANDOFF - M2 integration (branch m2-integration-6)

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

## Task wave-0 forensics - why the Forum planner QUITs in wave 0 (branch worktree-wf_fa16f06f-127-8, track diag)

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_fa16f06f-127-8` (from main bc46dc9). Facts: forum.md section 19
(Chinese, the full write-up with tables). Outputs (not in git): `C:\ssbot\data\m2_forum_w0f\` (drivers `fx_run.cmd`,
`fx_seen_run.cmd`, `ao_run.cmd`; per-episode forensics `fx\`, `fx_seen\`; `ao_all.json`). Frozen checkouts:
`C:\ssbot\live_w0f_417d4a8` (forensics batch), `live_w0f_fx2` (b4345c6, the seen replay), `live_w0f_ao` (81722c6,
attack outcomes), `live_w0f_3608489` (live check). Seeds used: 340000-340024.

### Findings (read this first)

- Every hit of the 225 analysed episodes (A0b 50 + the 7 overnight R5 / R6 arms 175; 949 damage events + 176 Multihit
  ticks) is inside the support (0 outside, L 2 / 3 / 4, union and own type). FORCED_RISK was on at the tick before
  every one of the 949. Sources: Envoy charge 205, Choristor whip chain 143, Envoy slash 100, Reed needle 88, Reed body
  80, Choristor jump spin 73, Envoy body 63, Choristor slash 63, Choristor body 51, Reed stab 48, Envoy jump slash 24,
  Reed parry counter 11. 0 kills in 225 episodes.
- **Root cause: the support saturates in wave 0, FORCED_RISK's ranking ties, and the pick falls to J.** At the last
  tick before every replayed hit (489 / 489) every candidate row is in the support on every non-invulnerable frame
  (share 1, frame 1 included); rows that the recorded future leaves clear and rows it hits have the SAME support share
  (274 / 274 ticks where both exist). Decomposed by placement group (2,854 ticks before hits): the Reed's start-later
  RE_STAB / RE_THROW / RE_IDLE bounding boxes EACH alone cover >= 99 % of the candidates on ~every tick, the Envoy's
  EN_CHARGE start-later box 92 %, plus committed windows; a median of 7-8 groups each saturate alone, so tightening one
  family (R5 value's finding) is not enough, and MultiForecast.committed() saturates too. With Pc / t_c / t_hit tied the
  p_k preselection and the order are J's; EVADE's stance comes from the same saturated risk map (= stay put), so the bot
  approaches / faces / swings at its target while believing every plan equally dangerous. Why R5 value / R6 v0 changed
  nothing is argued from their code, not tested: R5 adds terminal-value terms to J and kill value to the target
  weights (T48 also lengthens the horizon), R6 v0 changes the tactic, which reaches the planner as GoalPrefs (scores
  only); FORCED_RISK's keys come from the same saturated support in every arm. My replays of their episodes use main's
  planner and match their live picks 64 % (R5 015959) / 83 % (R6 L2 on 015904) / 98.5 % (R6 L2 off 020919). Their live
  outcomes (QUIT medians 11.8-16.5 s, 4.0-4.4 hits) are consistent with no effect.
- Hindsight (open loop, each row's nominal path vs the recorded damage colliders of the next 0.6 s): 78 % of the hits
  still had a clear row 0.15 s before, 99.6 % 0.6 s before. The "no information" claim rests on the saturation / tie
  evidence above, NOT on pick-vs-random rates: before a hit the replayed pick IS the executed plan (A0b 98.5 %), which
  was hit by construction, and open-loop hindsight favours unexecuted rows. (forum.md 19.5; the first version's
  "planner 9.4 % vs random 24.3 % six frames before a hit, worse than random" mostly measured that the hero was hit.)
  On the 316 ticks 1-12 frames before a hit where the replayed pick is NOT the executed one: pick 21.8 %, executed
  17.7 %, random 31.8 %, recorded-collider key 52.5 %. Over all ticks (every 3rd) pick 75.9 % vs random 75.0 %, biased
  both ways (near hits against the executed plan, away from hits for it).
- Not causes: kinematics (recorded keys rolled out over the last 12 frames, 413 non-Final direct hits: miss 15 = 3.6 %,
  error p90 0.17 u; over 24 frames the drift is larger, p90 0.67 u, 17 % > 0.3 u, 25 misses, so the second half of the
  36-frame horizon is less accurate), planner deadline (plan time > 16.7 ms: 3 of 28,561 ticks before hits, 14 of
  107,964 logged ticks = 0.013 %; whole ticks late 0.25 %), support holes (0).
- The person in the same wave-0 situations (forum_attack_outcomes, attack starts within 8 u): per-instance hit rates
  close to the bot's except Envoy charge (bot 43 % vs 1x 17 %: you jump over it, 75 % vs bot 41 %), Envoy slash (26 %
  vs 14 %: you are already airborne, 70 % vs 38 %), Choristor whip (38 % vs 21 %: you back off ~6 u and dash; the bot
  stays). The bot also faces more attacks (41 / min within 8 u vs 33) and never kills; you clear wave 0 (1x 24 / 46,
  0.5x 17 / 17) by killing the Envoy first.

### Fix tested: `ForumConfig.forced_rank = "seen"` (env `SSBOT_FORUM_FR=seen`, default `share` = unchanged)

- On FORCED_RISK ticks only, rows are ranked first by the frames their nominal box meets the damage colliders seen now
  (Entity.dmg_boxes active polygons) moved along their entity's velocity (`seen_contacts`, 0.14 / 0.54 ms p50 / p99),
  then the old share; the p_k preselection too. Safe ticks: keys all 0, order unchanged; Bell Beast not affected
  (ForumPlanner only). Offline, the recorded-collider version of the key (`dr`, multi-hit colliders included): pick
  clear in hindsight 45.7 % six frames before a hit vs random 24.3 %; 52.5 % vs 31.8 % on the ticks where neither is
  the executed plan. The production key replayed (`--forced-rank seen`): 58 % vs random 45 % within 12 frames.
- Live, instance 0, A0b protocol, seeds 340000 paired (control first, then fix; NOT the same load: late ticks share
  12.8 % vs seen 5.4 %; the effect is not load-driven, the 9 earlier share-type runs at 0.06-0.4 % late had QUIT
  medians 11.8-16.5 s): seen
  `C:\ssbot\data\runs\m2\20261008_040149_Forum_A_eval_planner_oracle` (24 QUIT + 1 HARNESS_FAIL "paused unasked")
  vs share `20261008_034918_Forum_A_eval_planner_oracle` (25 QUIT): time to QUIT median 19.1 vs 14.0 s, paired +5.0 s
  (95 % CI 3.4-6.6, longer in 23 / 24), hits / min 12.0 vs 16.5, Envoy charge hits 0.04 vs 0.92 per episode; still
  100 % QUIT in wave 0, 0 kills. A first seen chunk `20261008_034416` (6 episodes) ran while my offline batch loaded
  the machine (27 % late ticks, 1 HARNESS_FAIL): not counted. The seen arm's HARNESS_FAIL "paused unasked" is a
  known generic harness failure (48 attempts files across Bell Beast, Lace1 and older Forum runs), not seen-related.
- `forced_rank = "seen_cf"` (env `SSBOT_FORUM_FR=seen_cf`, 82e94fa): after the seen key, the share of stage-1 frames in
  the committed fine placements (`committed_fine_share`: attacks under way with a known entry; the windows and the
  start-later boxes, which saturate, are left out) - the strikes that open after their antic. Offline the hindsight-
  clear pick within 12 frames of a hit goes 60 % -> 73 % (random 45 %; whip 35 -> 68 %); both are counterfactual
  picks, but seen falls back to the executed order when its key is all 0, which biases it down - on the ticks where
  seen's pick is not the live one: 62 % -> 78 % (random 40 %). Live on instance 1 (instance 0 was
  r5value's), `20261008_045005_Forum_A_eval_planner_oracle`, 25 QUIT: time to QUIT median 25.2 s, hits / min 10.1
  (the person at 1x: 11.4). NOT paired with the two runs above (combat_run prefixes the seeds with the instance:
  1340000+), lighter machine load (1.3 % late ticks): unpaired seen_cf - seen +6.2 s (bootstrap 95 % CI 3.1-9.4),
  seen_cf - share +11.1 s (8.4-14.1). Still 25 / 25 QUIT in wave 0, 0 kills; the top remaining sources are the
  whip 0.64, Envoy slash 0.56 and jump slash 0.52 per episode.
- **seen_cf vs seen PAIRED** (review-fix round, 05:57-06:32, `C:\ssbot\sandbox\w0f_pair.ps1`): instance 0, frozen
  `C:\ssbot\live_w0f_cf` (82e94fa = final code), seeds 340100-340124, ABBA blocks of 5 (same instance, same seeds,
  alternating slots: late ticks 1.8 % vs 1.4 %). seen_cf runs `20261008_055737` / `060704` / `061017` / `062102` /
  `062440`, seen runs `060111` / `060410` / `061410` / `061752` / `062846`. Time to QUIT median 24.1 vs 19.4 s,
  paired mean +4.6 s (bootstrap 95 % CI 2.1-7.2), median difference +2.3 s (0.7-8.1), seen_cf longer in 18 / 25
  (sign test p 0.043); hits / min 9.4 vs 12.3; Envoy slash hits 0.60 vs 1.00 per episode. Both arms reproduce their
  earlier medians (seen 19.1, seen_cf 25.2). Still 50 / 50 QUIT in wave 0, 0 kills.

### Review fixes (verifier of 8fd77b0)

- forum.md 19.5 / 19.8 / 19.9 / 19.11: no more "the planner's picks are worse than random". Hit-conditioned pick rates
  are compared only against random or between counterfactual rankings, with the conditioning and the open-loop bias
  stated; the "no information" claim rests on the saturation / tie evidence. The split by "pick = executed plan" is in
  19.5 (scratch scripts `w0fx\split.py` / `split3.py`).
- 19.10: the seen / share pair did NOT run under the same load (late ticks 5.4 % vs 12.8 %); cross-run reference added
  (9 low-load share-type runs: QUIT medians 11.8-16.5 s), plus the paired, interleaved seen vs seen_cf re-run above.
- 19.6: kinematics at 24 frames too (non-Final 413: p90 0.67 u, 17 % > 0.3 u, 25 misses; all 489: p90 0.95 u); why 12.
- 19.4: "0.25 % of ticks plan > 16.7 ms" was the whole-tick late rate; plan time > 16.7 ms is 14 / 107,964 (0.013 %).
- 19.5: 2,854 of 2,871 decomposed ticks (17 empty), median 8 saturating groups; 19.9: the 45.7 % key is the
  recorded-collider `dr` key, not production `seen_polys`.
- 19.1 / 19.8: the R5 / R6 "only J / target" explanation is marked as argued from code (replay match rates 64 / 83 /
  98.5 %).
- The seen arm's HARNESS_FAIL is the generic "paused unasked" failure (48 attempts files), closed.
- Tests on 8fd77b0 code (the fixes since are docs only), in the worktree (git-ignored Forum hitbox npz present):
  full suite 1134 passed, 2 skipped (forecast vision window, hitbox-table timing on a busy machine), 1 xfailed; the
  six focused files 90 passed. From a git-archive export without the npz the verifier got 89 passed + 1 skipped.

### Running

- Nothing. The review-fix paired run (`w0f_pair.ps1`, instance 0) ended at 06:32 and released `inst0.lock` (r5value
  took it right after); instance 1's lock (04:46) was released at 05:05.
- Offline: nothing. The forensics replay covers 115 of the 225 episodes (A0b 50, R6 40, R5 25); the other 110 were not
  replayed so as not to load the machine next to the other tracks' live runs (`fx_run.cmd` resumes where it stopped).

### Needs deploy

- Nothing (no oracle change).

### Next / open issues

1. Merge `forced_rank` ("seen" / "seen_cf"; default stays `share`); the integrator's Forum A/B with
   `SSBOT_FORUM_FR=seen_cf` (paired against `seen` on the same instance and seeds: +4.6 s, above). It is orthogonal
   to R5 / R6 / R8 (only FORCED_RISK's first keys); their terms can only act once the tie is gone.
2. Antic-driven attacks (whip, Envoy slash, Reed stab, Choristor slash: over half of the remaining hits) are invisible
   to the "seen" key until their collider opens. A second key after it, the share of stage-1 frames in the committed
   fine placements (`forced_rank = "seen_cf"`, `SSBOT_FORUM_FR=seen_cf`, 82e94fa, tested), lifts the hindsight-clear
   pick within 12 frames of a hit from 60 % to 73 % offline (random 45 %; whip 35 -> 68 %, Choristor slash 0 -> 33 %;
   the Envoy slash stays hard, 19 -> 24 %) and lived 6 s longer than seen (above, unpaired). The real fix is a
   committed-attack template at its nominal (median dwell) timing instead of the entry-interval window union.
3. Support de-saturation (R2 / R3 owners, recertification needed): start-later families should not strike before
   their antic's minimum dwell; the flying Reed's idle growth capped by its measured top speed.
4. Offense: 0 kills in 274 live episodes; wave 0 never ends. R6's punish windows (Envoy Charge End, Slash1 Recover)
   should be re-measured under "seen".
5. Concurrent live runs raise tick p50 to 12-15 ms and late ticks to 5-28 % on this machine: compare arms paired under
   the same load; do not run offline batches next to a live check (it ruined my first fix chunk).
6. Frozen checkouts to remove when done: `C:\ssbot\live_w0f_417d4a8`, `live_w0f_fx2`, `live_w0f_ao`,
   `live_w0f_3608489`, `live_w0f_cf`.

## Task R8 - Forum clash (branch worktree-wf_814dfeea-b10-4)

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_814dfeea-b10-4` (from main bc46dc9). Plan: forum_planner_plan
R8 row and its notes. Outputs (not in git): `C:\ssbot\data\m2_forum_r8\` (drivers `clash_*.cmd`, stats `clash_*.json`
/ `.log`, replays `replay_*.json`). Facts: forum.md section 17 (Chinese).

### Done (committed)

- Wanderer support (the person: Wanderer over Reaper for clashing): `knowledge/1.0.30000/attacks/wanderer.json`
  (attack_table_build --crest Wanderer from the P17 slash dump; not live-sampled yet: side / up / wall slash on
  0-0.12 s from the swing (first animation event 0/24 s, like Hunter: clash chains are seamless), down slash
  0.04-0.16 s; Clash Tink boxes per slot); `kinematics/hero_wanderer_forum.json` (the Reaper Forum loadout with the
  Wanderer config: duration 0.25, cooldown 0.3, recovery 0.1; abilities without reaper_down, with the new
  `AB_DOWN_SLASH` (DownSlashTypes.Slash: the down attack is an ATTACKING swing, no dive / FSM); thunk polygons and
  windows from the Wanderer table); `kin_jit` handles AB_DOWN_SLASH and the new event `EV_PARRY_RECOVER`
  (NailParryRecover 0.1 s after a clash: attack cooldown 0, the swing cancelled). Both bits are unused by the Hunter
  / Reaper parameters (Bell Beast and the Reaper Forum rollouts unchanged by construction).
- `ForumPlanner(crest=...)`: the crest's shapes (a Slash-type down slash timed like the other slots), the kernel
  classifies a Wanderer down slash (B_DOWN in the air) and vetoes an attack pressed within 0.15 s after a dash / sprint
  frame (DASHCOMBO_WINDOW_TIME: the press would be the WANDERER DASH COMBO, not modelled); the kernel also returns
  each row's first swing.
- EV_CLASH (`ForumConfig.clash`, off by default = the R3 / R4 planner): only on ticks with no safe row (plain safe rows
  always rank first), up to 16 rows in contact (by J) whose first contact on the envelope falls inside a swing's
  active window, attributed to enemies (`occupied_only` at the hull centre) whose current attack family is in
  `clash.json` for that slot and that are on the slash's side; success branch = the clash on the frame before the
  contact, PARRY_INVULN_F 9 frames without enemy damage (any source: the two-sided rule), the direction's recoil
  (side away from the facing, up RecoilDown, down the bounce), EV_PARRY_RECOVER 6 frames later; a later contact may be
  clashed again (chains, the other side) up to 3 times; p_fail = 1 - prod(1 - p_k) <= clash_max_fail 0.25 and h >= 2
  -> the row counts as safe (ranked after plain safe rows by p_fail). `res.clash`, audit clash_ticks / clash_rows /
  clash_chosen, policy counts clash_plan.
- `ssbot.tools.forum_clash_stats`: clash setups (the clash reach meets an enemy's canClashTink collider before any
  hurtbox contact) and contact setups (the planner's rule: the enemy's first contact inside the swing's window) with
  outcomes clash / hit / neither by crest x type x family x state x slot; after-clash chains and blocked damage;
  `--table` builds `knowledge/1.0.30000/enemies/forum/clash.json` (Wilson 95 % upper bound of the hit share,
  n >= 10, Clapper / Tiny / Bellbearer / Clawmaiden spear / body families never).
- `Forum_W` encounter (fo_W), `combat_run --forum-clash` (run tag `_clash`), `ForumPlannerPolicy(crest, clash)`
  (crest from the savestate: fo_W Wanderer), `forum_policy_replay --clash --crest`.

- Clash continuations (`candidates.build_forum(clash=True)`, only with clash on): keep swinging every 8 frames
  (N / L / R / U): a second clash after NailParryRecover, the other side, the up slashes under the Minister.

### Measured so far (offline)

- Open-loop replay of A0b i1 ep0 (648 ticks, 483 FORCED_RISK, the machine busy): with a permissive test table
  (every statically clashable family p 0.1) the clash branch ran on 483 ticks, looked at 7,200 rows, 234 had a swing
  active at the first contact, all 234 attributed, 59 to clashable families on the slash's side, 7 clean success
  branches (3 chosen); without the clash continuations 0 clean (the support still covers the hero after 0.15 s).
  Clash branch 2.4 ms per forced tick; plan p50 6.5 -> 8.4 ms with the extra rows (busy machine).
- The person's sessions (5, 4,439 swings, 239 clashes): clash setups (clash reach meets a clash collider before any
  hurtbox contact) almost never end in a hit (e.g. Wanderer Minister charge up 7 / 10 clash, 0 hit); contact setups
  (the planner's rule) do: Choristor slash side 14: 7 clash, 3 hit; Reed stab side 11: 3 clash, 4 hit. The R1 v2
  data2 runs are being counted (below).

### Running

- Offline stats (hidden, below normal; this worktree's code): `C:\ssbot\data\m2_forum_r8\clash_d0..d3.cmd` (the 36
  data2 runs split four ways), outputs `clash_d*.json` / `.log`; `clash_h.json` (the person's sessions) is done.
- Live driver `C:\ssbot\sandbox\r8_live.ps1 -co C:\ssbot\live_r8_c1ca21a` (hidden, log `C:\ssbot\sandbox\r8_live.log`):
  builds `clash.json` from the stats when all five exist (into the checkout and `m2_forum_r8\clash_table.json`;
  commit it to the branch afterwards), warm replay (aborts on failure), waits for the Trobbio collection to end,
  takes `locks\inst2.lock` / `inst3.lock` ("r8"), Wanderer slash frames probe on instance 2 (fo_W, 60 swings,
  `C:\ssbot\data\runs\m2\kn_excite_forum_wanderer`), then three arms of 25 + 25 full gauntlets on instances 2, 3
  (eval, oracle, real quits 0.2, the A0b protocol): R8W = Forum_W + --forum-clash (seed 320000), W0 = Forum_W
  (320200), R8R = Forum_A + --forum-clash (320400); per arm forum_a0_report and forum_clash_stats into
  `m2_forum_r8\report_<arm>.json` / `clash_live_<arm>.json`; releases the locks, logs R8_DONE. Stops after the
  current episode on STOP_AGENTS / DEMO_SOON. Stop now: `combat_run stop <run dir>` from the checkout's brain, then
  delete the two lock files if the driver did not.
- kin_check of the Wanderer / Reaper parameters on the fo_W session 20261004_012300 (`m2_forum_r8\kin_*.json`).

### Stopped (2026-10-08 00:45 PDT, weekly usage 99 % before the 03:00 reset; the stop protocol)

- Left running on purpose (correctly configured, both mine): the five offline stats batches (`clash_d0..d3.cmd`,
  `clash_h.cmd`, this worktree's code at c1ca21a, union setups; the first version's outputs are kept as
  `clash_*_v1.json`) and the live driver above (it waits for them, then for the Trobbio run, then takes the locks).
- A0b report for the comparison: `C:\ssbot\data\m2_forum_r8\report_A0b.json` (forum_a0_report over 205437 +
  205857: 51 episodes, QUIT 50 (Q1), HARNESS_FAIL 1, 4.27 hits per episode (Envoy 105, Reed 57, Choristor 56, all wave
  0), FORCED_RISK 80.3 %, 1 hit outside the support).
- The first table (contact setups only, `clash_table_v1.json`) admitted at p_fail <= 0.25 only the Minister charge
  (side 563 setups, 457 clash, 13 hit, UB 0.039), Choristor slash side (0.19), Choristor whip side (0.22), Maestro
  slash up (0.20), Minister charge down / up (0.15 / 0.19), Envoy slash down (0.14), Reed defend down (0.17); Reed stab
  side 0.47, Clawmaiden slash side 0.28, Minister counter side 0.25. Contact setups miss the clashes that kept the
  attack off the hurtbox, hence the union rerun.
- Wanderer kinematics on the person's fo_W session (kin_check planner_bounds, bounds_lo_mix): Wanderer parameters
  0.6911 all / attack windows 0.9846 / contact 0.9398 vs the Reaper parameters 0.6879 / 0.9823 / 0.9319 (the session
  includes the bench runs, deaths and dashes: dash 0.81 for both, as R3 found on live Forum data).
- Full test suite at 43aeef5: 1135 passed, 2 skipped, 1 xfailed.

### Next / open issues

0. When the driver logs R8_DONE (`C:\ssbot\sandbox\r8_live.log`): commit `C:\ssbot\data\m2_forum_r8\clash_table.json`
   as `knowledge/1.0.30000/enemies/forum/clash.json` (the worktree's untracked clash.json was a permissive test table,
   deleted); fill forum.md 17 (union table, live clash outcomes per arm, A/B) and the plan's R8 note.
1. After the driver: compare the arms with A0b (CLEAR / QUIT / WOULD_DIE, hits per episode, waves, time alive,
   support-outside hits, tick p50 / p99), the live clash outcomes per family, Wanderer frames ->
   `attack_table_build --crest Wanderer --live <rec>\attack_frames.jsonl`; forum.md 17 and the plan's R8 note.
2. Not done: the Minister-from-below up-slash experiment (the clashrepU rows give the planner the move; no scripted
   probe); the javelin (Reed Pin Projectile, clashable) is a hazard path the branch does not attribute; the
   PARRIED-interrupted attacks (Envoy charge -> Deflect, Reed counter -> Multihit Clashed) keep their remaining support
   in the success branch (conservative); the supervisor does not see a clash plan's failure risk (S = 0, P 0; clash
   rows need h >= 2); VE view rates = oracle's (no VE data).
3. The Bell Beast: the shared changes are new bits / branches only (AB_DOWN_SLASH, EV_PARRY_RECOVER, build_forum's
   clash flag): bit-identical by construction; the full test suite is the check (running at the time of writing).

### Round 2 (2026-10-08 03:00-, week push round 2; main bc46dc9 merged: no change)

Round 1's driver `r8_live.ps1` built the clash table and then stopped at 01:08 on "warm replay failed": the replay
had succeeded (`warm_replay.json` written), but `Start-Process -PassThru` without a cached `Handle` gives no ExitCode
in Windows PowerShell 5.1 and the check read `$null` as a failure. Replaced by `C:\ssbot\sandbox\r8_live2.ps1` /
`r8_live3.ps1` (handle cached, the arm's run dir from combat_run's own "run dir:" line in r8_live3; r8_live2 took the
newest run dir, another track's: its `report_<arm>.json` for R8W / R8R / R0 were redone by hand with
`C:\ssbot\data\m2_forum_r8\live\arm_report.cmd NAME RUNDIR`, the wrong ones kept as `*_wrongdir.json`).
Outputs: `C:\ssbot\data\m2_forum_r8\live\` (reports `report_<arm>.json`, live clash stats `clash_live_<arm>.json`,
consistency checks `check_<arm>.json` from `scratchpad/r8/clash_live_check.py`).

Done (committed):
- `clash.json` committed (64a48cc; union setups of the R1 v2 data2 runs + the person's sessions: 33 keys, 18 at
  p_fail <= 0.25, 29 at <= 0.5; forum.md 17.3).
- Wanderer slash windows measured live (instance 2, fo_W, 60 swings, seed 320000, recording
  `C:\ssbot\data\runs\m2\kn_excite_forum_wanderer\...\kn_excite_forum_s320000`): side / alt / up frames 1-7, down
  3-9 (`attacks/wanderer.json` frames); clash chains are seamless (new swing on at c+7, same collider clashable from
  c+7, i-frames to c+9; Reaper 5-12: 2-frame gap). `attack_table_build --live` folds the probe's second press of any
  slot (it read Wanderer's second swings as one 1-38 window).
- The Minister-below experiment: `Forum_W_w4` (`fo_r8_w4w` = `fo_r1_w4` + Wanderer, `ssbot.probes.forum_states
  wanderer`), `--policy minister_below` (`forum_policy.MinisterBelowPolicy`: under the nearest Minister, up held,
  attack every 4 frames), 30 x 20 s on instance 3 (seed 321000, run `20261008_032228_Forum_W_w4_data_minister_below_oracle`).
- Clash branch v2 (895137b): the PARRIED-catching attacks (Envoy charge, Reed counter) end at the clash (support
  frozen at the clash frame, hull grown by the measured post-clash motion `PARRY_STOP_GROW`, forum.md 17.5); one
  committed clashable owner suffices (idle co-owners are covered by the parry i-frames, a co-owner in its own attack
  blocks); partial clashes (contact left after the clashes) enter FORCED_RISK's ranking with the share p_fail x
  share without + (1 - p_fail) x the branch's (`clash_partial_max_fail` 0.5); the branch is skipped when no enemy is
  in a clashable attack; the decision log's `clash` field. Tests: test_forum_clash.py 8.
- `hero_damage.KNOWN_NEUTRAL` + Cogwork Flier, Wallcling (603fc7b): unlisted, they added the imbuement / Barbed Wire
  bounds (nail 16), and with the Wanderer's x3 crit the bound was 48 >= every wave-0 HP: the killing-blow rule
  (YELLOW / RED, Forum kills never certifiable) withheld every swing in YELLOW. Logged nail hits with both tools: 9 /
  10 / Wanderer crit 27, never more. Bell Beast's loadout has neither tool: unchanged. (Review: it also lowers the
  default Forum Reaper's bound 16 -> 9 / 10, so YELLOW withholds the nail on fewer ticks; A0b, R0 and R8R ran at 16.
  The Reaper arms are rerun at the new bound in the review fixes below.)
- forum.md 17.1, 17.3, 17.5-17.8; a stray form feed in forum.md 13 repaired.
- Full suite at 895137b (worktree): 1137 passed, 2 skipped, 1 xfailed; test_kill_rule.py 41 passed at 603fc7b.

Measured (live, A0b protocol, 50 episodes per arm, instances 2 / 3; forum.md 17.7 / 17.8):
- Every arm 50 / 50 QUIT in wave 0 (Q1), 0 kills, 0 hits outside the support. Time to QUIT median / hits per min /
  Envoy-charge hits per episode: R0 (Reaper, clash off, 895137b, seed 320600, `20261008_042706`) 11.92 s / 19.7 /
  1.10; **R8R** (Reaper + clash, 320400, `20261008_041514_..._clash`) **13.75 s / 18.0 / 0.60** (+1.83 s, 95 % boot
  CI about 0.0-3.0); W1 (Wanderer, 603fc7b, 320800, `20261008_044219`) 11.98 / 20.8 / 0.78; R8W1 (Wanderer + clash,
  320800 paired, `20261008_045259_..._clash`) 11.72 / 21.6 / 0.82 (no effect). A0b 12.81 / 19.1 / 1.08. Void:
  W0 / R8W (`20261008_040450` / `035419`, nail withheld by the 48 bound): 10.2 / 10.6 s.
- Clash plans chosen: R8R 18 clean + 218 partial ticks, R8W1 88 + 930. Consistency (streaks of clash ticks, the next
  36 frames of the recording): R8R 18 streaks, 4 clashed, 5 hit (all before a clash), predicted p_fail 0.26; R8W1 82,
  14 clashed, 19 hit (16 before a clash), predicted 0.29. Live clashes (forum_clash_stats): R0 104, R8R 151, W1 109,
  R8W1 117 (Envoy charge setups R8R 48: 39 clash, 1 hit).
- Compute (loaded machine: other tracks' live runs on 0 / 1 / 4 and offline jobs): plan p50 R0 4.5 / R8R 8.8 ms, W1
  4.1 / R8W1 5.3 ms; late ticks R0 7.0 % / R8R 36.5 %, W1 3.7 % / R8W1 4.9 % (review: not the machine; R0 overlapped
  the same busy instance-0 run longer and stayed at 7 %: the clash branch's own 2.2 ms per clash tick, no deadline).
- Minister below (Wanderer, continuous up slash, 30 x 20 s): up slash meeting the charge: of 114 clash setups 65
  clashed, 0 hit, 49 neither (review correction: not "65 / 65"), union setups 55 clash / 1 hit of 101 in front; parry
  counter worse (4 clash / 3 hit of 27); overall 14.9 Minister hits per Minister-minute (data2 random policy, 205 w4
  starts: 20.2; per episode is not comparable: 20 s-capped episodes vs 180 s ones), both dead in a median 10.7 s
  (data2 71 s); hits: charge from the side 38, the parry stance body 33, the body 15.
- Tie to the diag track (HANDOFF "Task wave-0 forensics", forum.md 19): wave 0's support saturates and FORCED_RISK
  ties; the clash branch only acts on ticks with an enemy in a clashable attack (its parry i-frames lower the
  saturated share), so it moves the Envoy charge and not the wave-0 outcome. Its `forced_rank = "seen"` (+5.0 s live)
  is the bigger step; when both are on, seen counts the collider the swing would clash as a contact and ranks clash
  rows last: the clash branch's success contact should replace seen's for those rows (integration).

Running: nothing. Locks inst2 / inst3 released (r8_live2 / r8_live3 logged R8_DONE).

Needs deploy: nothing (no oracle change).

Next / open issues (round 2):
1. Clash is not a wave-0 fix: Reaper +1.8 s (CI touching 0), Wanderer flat. Not written into `Forum.yaml`; the plan's
   acceptance (hits and quits not more) holds for the Reaper and is flat for the Wanderer. Re-measure with
   `forced_rank = "seen"` merged (seen + clash vs seen), the clash rows' seen contact replaced by the branch's.
2. The killing-blow rule with the Wanderer's x3 crit bound (27 at needle 1) withholds the nail in YELLOW once any
   enemy may be at <= 27 HP (37 % of W1's ticks vs 17 % for the Reaper, measured at its old bound 16): a structural
   cost of the Wanderer under the current safety rules (the crit chance is about 1 %: 4 of 403 logged hits).
3. Cost: partial clashes roll out 16 rows x 3 levels; try clash_k 8 / clash_depth 2 before the integrator's A/B
   (R8R's late ticks were 36.5 % on a busy machine).
4. DESIGN 3.5.6's parry whitelist says no parry / clash in YELLOW / RED (`Restrictions.no_parry`; the clash freeze
   swallows a pause); the clash branch only requires h >= 2 (PAUSE_PENDING allows no attack at all). The lead should
   confirm that R8's rule replaces the whitelist for the Forum, or the branch must read `no_parry`.
5. Still open from round 1: the Reed javelin is clashable but not attributed; the supervisor does not see a clash
   plan's p_fail; VE view rates = oracle's; the Wanderer kinematics are not refitted on Wanderer recordings; the
   wall slash's live frames were not sampled (the probe swings no wall slash); the Clash Tink collider's window is
   taken as the damager's (not sampled).
6. My mistake to avoid: running `C:\ssbot\tools\uv\uv.exe run` in a frozen checkout WITHOUT
   UV_PYTHON_INSTALL_DIR made uv delete the checkout's `.venv` (Lib) while an arm was using it (W0 survived; the next
   `uv run` with the variable rebuilt it). Use scripts/uv.cmd or set the variable.
7. Frozen checkouts to remove when the integrator is done: `C:\ssbot\live_r8_c1ca21a` (round 1),
   `live_r8_64a48cc` (Minister run), `live_r8_895137b` (R8W / W0 / R8R / R0), `live_r8_603fc7b` (W1 / R8W1).

### Round 2 review fixes (2026-10-08 05:30-, the fixer; verdict on 67b28d6)

Done (committed):
- `forum_clash_stats` (532f8e2): union setups keyed by the enemy's Control state and carrying their attack instance
  (the enemy's run of frames in one family), the worse outcome of the two views (hit > clash > other > neither),
  Multihit special damage owned by the nearest damaging enemy (was never counted), the Reaper down window [9, 19]
  as the planner's. `build_table`: each family's clashable states (where its clashes happened, >= 2 and >= 5 % of
  them), rates over those states only, `p_clash_lb` (Wilson lower bound of clash / n) and `p_fail` (upper bound of
  hit / n) at n_eff = the attack instances, per-crest rows with their own bounds.
- `clash.json` rebuilt (d24ef17; stats `C:\ssbot\data\m2_forum_r8\fix\clash_*.json`, driver
  `C:\ssbot\sandbox\r8f_stats.ps1`, checkout `C:\ssbot\live_r8_532f8e2`): the 36 R1 v2 data2 runs, the person's 5
  sessions, the round-2 live runs and A0b; 31 keys, 19 at p_fail <= 0.25, 10 at p_clash_lb >= 0.5, none at 0.75
  (best: Minister charge side 0.74 / 0.044, Envoy charge side 0.72 / 0.047); clashable states e.g. Envoy charge
  {Charge}, Reed counter {Parry Slash}, Reed stab {Stab 1, 3, 5}, Minister charge {Attack}.
- Clash branch v3 (f1f2fb1, d997bc7): the branch's weight w = prod p_clash_lb (a setup that neither clashed nor was hit
  gave none of the clash's effects); a clean branch is a safe row only at w >= 0.75 and hit risk <= 0.25, any other
  (w >= 0.25) is ranked in FORCED_RISK by w x the branch's share + (1 - w) x the plain row's (first contacts stay the
  plain row's; such rows always join the ranked candidates); eligibility by state: `clash_windows` (the walk's dwell /
  successors inside the family) must let the owner be in a clashable state at the clash, PARRY_STOPS by state (Envoy
  Charge / Reset, Reed Parry Slash); DESIGN 3.5.6: GREEN only by default (`ForumConfig.clash_tiers`), never with a
  pause pending; `combat_run --forum-clash {on, yellow, cont}` (yellow: GREEN and YELLOW, the experiment; cont: the
  clash continuation rows without the branch); deadline per level (`clash_deadline_ms`, default deadline_ms + 2),
  clash_k 8, clash_depth 2; candidates whose first swing is out at their first contact first; parry i-frames 9
  frames, from j_hi to (the earliest frame the clash reach can meet the owner's support) + 9; co-owners no longer
  block (the parry i-frames take every enemy's damage; the branch meets their support after them; counted
  `clash_coowned`); the decision log's `clash` is now [w, clashes, ranked].
- Window semantics: the kernel already scores the last active frame (`_shapes` gives [f0, f1 + 1)); the clash pass's
  frame is in the same half-open window; the stats' Reaper down slash now matches (test).
- Tests: test_forum_clash.py 20 (windows, the table builder's states / n_eff / crest rows, the owner rule, a no-way-out
  synthetic Reed tick: the branch runs and ranks; gates: YELLOW, pause pending, h 1, branch off, state outside,
  no states; a skipped pass leaves the tick as the continuation rows alone make it).
- Docs: forum.md 17.7 / 17.8 corrections (65 of 114, per-minute only, the Reaper bound, the A/B not significant, the
  late-tick attribution), `{BS}` placeholders replaced (HANDOFF, forum.md). The commit message of 64a48cc says 44 keys:
  the committed table then had 33.
- Open-loop replay A0b i1 ep0 with v3 and the provisional table (`--clash yellow`): 483 forced ticks, 210 swings out at
  the contact, 166 owners outside their clashable states (mostly Envoy JumpSlash 4 / Choristor Slash Recover), 38
  clashes accepted (all Envoy charge / Reed counter stops), 38 ranked, 4 chosen; 8 levels cut by the deadline; plan
  p50 5.3 ms (v2: 9.8 ms), clash 0.96 ms per forced tick.

Measured (live, forum.md 17.9): `C:\ssbot\sandbox\r8f_live.ps1 -co C:\ssbot\live_r8_d24ef17` (06:08-08:30, log
`C:\ssbot\sandbox\r8f_live.log`, manifest `C:\ssbot\data\m2_forum_r8\fix\ab_manifest.txt`, 12 runs): 4 blocks x 3
arms (order rotating), each run 25 + 25 Forum_A gauntlets on instances 2 / 3 (A0b protocol, Reaper at the new bound
9), block seed 322000 + 100 x block for every arm, so 200 episodes per arm paired by seed. Analysis
`C:\ssbot\data\m2_forum_r8\fix\ab.py <manifest> <out.json>` -> `ab.json` (sign-flip permutation on the pairs,
bootstrap CI, unpaired permutation); consistency `check_RY.json` (round 2's `scratchpad/r8/clash_live_check.py`;
its "p_pred" is now w). All 600 episodes QUIT (Q1) in wave 0, WOULD_DIE 0.
- R0 (clash off): alive p50 / mean 13.76 / 14.16 s, 4.19 hits / ep, 17.8 / min, HP lost 21.1 / min, Envoy charge
  1.02 / ep, late 2.4 %, plan p50 4.0 ms.
- RC (`--forum-clash cont`, the continuation rows only): 13.25 / 13.37 s, paired -0.79 s (p 0.003, CI -1.31..-0.27),
  hits -0.18 / ep (p 0.01), Envoy charge 0.68 / ep (-0.35, p < 1e-4), HP lost 22.4 / min, 2 kills.
- RY (`--forum-clash yellow`, the branch in GREEN + YELLOW and the rows): 12.93 / 13.69 s, paired -0.47 s (p 0.11, CI
  -1.03..+0.09), hits -0.15 (p 0.047), Envoy charge 0.63 (-0.40, p < 1e-4), HP lost 21.9 / min, late 2.9 %, plan p50
  5.2 ms, 1.12 ms per clash tick, 2 % of clash ticks cut by the deadline, 2,724 chosen ranked clash ticks.
- RY vs RC (the branch alone): +0.32 s (p 0.22), Envoy charge -0.05 (p 0.50): no measurable effect.
- Consistency (RY): 207 chosen clash-plan streaks, 48 % clashed, 19 % hit (36 of 39 before a clash), w mean 0.58;
  base rate of all forced ticks 46 % hit / 11 % clash within 36 frames (not a calibration test: event-sampled log).
- Reading: round 2's Envoy-charge drop comes from the always-swinging continuation rows (the charge runs into the
  blade), not from the branch; the rows also swing far more (4.2 vs 1.6 presses / s), move the damage to the
  Choristor and shorten survival; the branch has little to do in wave 0 (most swings out at a contact meet an enemy
  in its recovery, not clashable; no key reaches w 0.75). Neither arm is written into Forum.yaml.

Running: nothing. Locks inst2 / inst3 released (R8F_DONE 08:29).

Tests: full suite (`tests` + `ssbot/tests`, NUMBA_NUM_THREADS 4, below normal) at d24ef17: 1150 passed, 2 skipped, 1
xfailed (log `C:\ssbot\data\m2_forum_r8\fix\pytest_full.log`); test_forum_clash.py 20 passed. Bell Beast: the changes
are in the Forum planner / policy / combat_run's Forum switch / the clash stats tool; its equivalence tests pass.

Needs deploy: nothing (no oracle change).

Next / open issues (after the review fixes):
1. Clash is not worth turning on as built: the continuation rows cost 0.8 s of survival (p 0.003) for -0.35 Envoy
   charge hits / episode, the branch adds nothing measurable on top. If anything is kept, it is the observation that a
   blade held out stops the Envoy charge: a targeted "swing into the charge" row (only when an Envoy is in Charge
   Antic / Charge facing the hero) instead of always-swinging continuations, A/B'd the same way.
2. DESIGN 3.5.6 decision for the lead: the branch now follows the whitelist by default (GREEN only, no pause pending);
   `--forum-clash yellow` / `clash_tiers` is the experiment. In wave 0 about 85 % of ticks are YELLOW, so the
   compliant setting barely runs.
3. No clash.json key reaches p_clash_lb 0.75 (Minister charge side 0.74, Envoy charge side 0.72): no clean clash row
   can be a safe row; all go through FORCED_RISK's mixture. More clash data (the Wanderer especially: its keys have
   n_eff 10-87) would narrow the bounds.
4. Integration: when forced_rank "seen" / commit_rank (diag / R5 value branches) merge, the clash rows' FORCED_RISK
   keys need the branch's mixture too (seen counts the collider the swing would clash as a contact). forum.md section
   numbers collide: the R5 value branch also writes 17.5-17.10 under its own section 17; renumber R8's at integration.
5. The parry i-frames in the branch mask every support the planner queries (enemy_only or not); thrown hazards that
   the parry i-frames do not cover (DESIGN: they do not stop hazard-type damage) would be under-counted if any Forum
   source is a true hazard type (the Reed javelin / bells deal ENEMY damage as far as known; not verified).
6. Still open: the Reed javelin is clashable but not attributed; the supervisor does not see a clash plan's risk;
   VE view rates = oracle's; the Wanderer kinematics not refitted on Wanderer recordings; the wall slash's live frames
   not sampled; the Clash Tink window taken as the damager's.
7. Frozen checkouts to remove after integration: `C:\ssbot\live_r8_c1ca21a`, `live_r8_64a48cc`, `live_r8_895137b`,
   `live_r8_603fc7b`, `live_r8_532f8e2` (stats), `live_r8_d24ef17` (this A/B).

## Task harness recovery (branch worktree-wf_814dfeea-b10-6, 2026-10-08)

Facts: `docs/facts/1.0.30000/pause_quit.md` section 11 (Chinese). Training profile only: safety/pause_quit and the
supervisor are untouched, the formal-run path gains no key.

Signatures found (all attempt rows / worker logs / STATE recordings of 2026-10-01 .. 07):
- (b) "paused unasked": 60 of 61 were the oracle's brain-lost watchdog (STATE act.lost, the Pause bit in the injected
  mask on the pause frame, last ACTION applied 13-15 frames before): the worker's fight loop stalled >= 250 ms (first
  compiles at ep 0 / 1, CPU contention, four runs in the same second on 10-04 21:01:15). Not a stray Esc, not focus
  (half had focus, the game does not pause on focus loss). The one other (20261006_065605_Lace1_data i0) had no Pause
  key at all: InputHandler.ControllerDetached is the only other way into PAUSED (a gamepad going to sleep?).
- (a) the "settings menu": 20261005_164501_Forum_A_w2_mix_data2_2 i1 at 16:45 sat in the title's Game options (menu
  12): load_slot's retried Enter on a main menu highlighting Options (mouse hover / a cursor over the new window) went
  Main -> Options -> Game options -> a setting, then waited 2 x 60 s for the main menu and died. Same minute, instance 4
  (20261005_164455_..._inject) Enter'd Extras and then the credits. The old unpause() had the same blind Submit in game.
- (c) "kept running while the hero stood still being hit" (Forum data2, 10-05 / 06, 961 episodes, ~49 h): not a
  stall. 1944 no-key windows >= 1.5 s with 1062 hits, every one inside an episode with ACTIONs applied each frame, no
  lost brain, no pause; they are the data2 policy's own waits (WALL_BAIT 920 windows / 786 hits, CLASH, UNDER,
  JUMP_OVER, BAIT); between episodes 2-7 s of reset. The 180 s timebox resets at once.
- Also: 10-05 14:15 all instances' frame rate fell to ~4 fps (machine-level; the 5-in-a-row stop was right);
  20261002_080522 i0 "left the scene: Quit_To_Menu" then failed 3 episodes on "no game loaded" (no way back).

Done (commits 7ba7470, 0a326c3, 02469ab):
- `ssbot/train/recovery.py`: where() (title / title sub-menu / save select / quitting / pause menu / exit prompt /
  pause sub-menu / opening / game), pause_cause(), resume() (Up to Continue, Down to Back, Down to No, Submit only on
  those roles, never Esc, lockout respected, input.release before and after, <= 24 navigation taps), title_home() (Esc
  on title sub-menus only).
- `episode`: unpause() = resume(); a pause before the reset that does not end -> HARNESS_FAIL "still paused before
  the reset" (no hang); "paused unasked at frame N (<cause>)"; AttemptRecord.loop_gap_ms_max / loop_gaps_250.
- `probes/common.load_slot`: Enter retried only while still on the main menu; another menu -> MenuError; a title
  sub-menu is left first.
- `combat_run`: _unstick backs out of title sub-menus and moves Up towards Start Game after a MenuError, resumes a
  paused game instead of loading under the pause menu; worker start resumes; after_harness_fail() after every
  HARNESS_FAIL (paused -> resume; quitting -> wait for the title; title / sub-menu / save select -> back_into_slot);
  summary: harness_fails by kind, loop_gap_ms.
- `probes/recovery_check.py`: live check of every case on one instance.
- Tests: `tests/test_harness_recovery.py` (26, a stand-in game with the pause / options / prompt / title menus);
  the full suite at b10b251: 1141 passed, 3 skipped, 1 xfailed (an earlier run under load failed only the known
  timing budget test_hitbox_tables::test_support_query_matches_reference_and_meets_the_budget, 3.39 ms > 3 ms).

Round 1 stopped 2026-10-08 ~01:00 PDT (weekly usage 99 %) before the live check. Round 2 (2026-10-08 03:10 - 03:45
PDT, commits 6921f95, 76d5b36, 8148fd4, 2e11ffe):
- `recovery.pause_cause`: act.lost -> the watchdog (BrainLost stays set until the next ACTION, so the first paused STATE
  of a watchdog pause always shows it); a Pause bit in the harness's own ACTION with act.lost false -> "a Pause key in
  the harness's own ACTION (policy / probe)" (was counted as the watchdog).
- `combat_run` worker: a pause still showing before the next episode is resumed before set_time_scale (a paused game
  reads Time.timeScale 0 and set_time_scale stopped the worker: 20261008_015907 i0); still paused -> no scale read, the
  episode's start check makes it a HARNESS_FAIL (5-in-a-row stop); set_time_scale's stop names a pause.
- `probes/recovery_check`: two episode cases (PauseAt wraps the data policy and presses Pause mid-fight from the
  harness side): episode_pause (HARNESS_FAIL, after_harness_fail, a second episode) and episode_settings (then the
  pause menu's Options -> Game, the next episode's own start resume, no after_harness_fail). Seeds 990000+ (probe
  only, no attempt rows).
- Sample 20261008_015907_Forum_A_eval_planner_oracle i0 (r5value A/B, code 35e5fe6, before the recovery code): the
  only HARNESS_FAIL in 1104 episodes of 10-07 / 08. Watchdog signature (last ACTION applied 12361193, act.lost at
  12361207, paused 12361208); cause: one planner decision of 1599 ms (decisions_i0 f 12361192, plan "WAIT+runR"; the
  other 235 decisions median 3.6 ms, max 15 ms) after an 8.3 s warm-up. The old worker left the pause and stopped on
  "time.scale 1.0: the game runs at 0.0": the run has 1 episode. Both halves are handled now.
- Live check on instance 4 (lock ops 03:37:27 - 03:40:02, frozen `C:\ssbot\live_recov_8148fd4`): all 10 cases ok,
  every Submit on continue / back / no, no Esc while paused. `C:\ssbot\sandbox\recovery_check\20261008_033740_i4.json`.
  The real Options (menu 2) and Game options (menu 12) reach Back with Down x5 (nothing named before it); the
  watchdog case paused 252 ms after the last ACTION, cause "brain-lost watchdog, last ACTION applied 14 frames
  before"; after Esc back from the title's Options the main menu highlight stays on Options, so load_slot's first
  Enter is a MenuError and the second try gets in (11.8 - 13.7 s); both episode cases: ep1 HARNESS_FAIL "paused
  unasked ... (a Pause key in the harness's own ACTION ...)", ep2 ran its 12 s timebox (STUCK, 704 / 719 ACTIONs),
  loop_gap_ms_max 19 - 25 ms. Instance 4 was in routes' Song_Tower_01 at the start; it was left in Bone_05 (Bell
  Beast savestate), unpaused, save suppression on. Facts: pause_quit.md 11.3.
- Tests: test_harness_recovery.py now 27 (+2 tests: PauseAt's press timing, set_time_scale naming a pause; the
  harness's own Pause cause is an assert added to test_pause_cause, not a new test). Full suite at 8148fd4: 1155 passed, 3 skipped, 1 xfailed (NUMBA_NUM_THREADS 4, below-normal
  priority).

Round 2 fixer (2026-10-08 04:00 - , commits 3b18248, 772dfe8, ef67b89, f0dba93 and on), after the verifier:
- `combat_run.ready_for_episode` / `after_episode` (out of the worker loop, so they are tested): a pause still showing
  before an episode is resumed before set_time_scale; still paused -> that episode is NOT run (it would have run
  without the time scale set when its own start resume worked), its row is HARNESS_FAIL "still paused before the
  episode (...)" with time_scale_game None, and the 5-in-a-row stop ends a worker that cannot recover. After the row:
  real quit -> back_into_slot; HARNESS_FAIL -> after_harness_fail (exceptions logged).
- Worker-loop tests: `combat_run.main(["_worker", ...])` on the stand-in game (OracleLink / run_episode / make_policy
  patched): watchdog pause -> after_harness_fail resumes -> next episode at time scale 1.0; after_harness_fail doing
  nothing -> ready_for_episode resumes (the 015907 path); a pause no resume leaves -> no run_episode, 5 rows, stop, no
  SystemExit. Plus ready_for_episode by place, PauseWatch. test_harness_recovery.py: 33 (+6).
- `recovery.PauseWatch` (on FightTap / GauntletTap as `tap.pause`): the cause of "paused unasked" comes from the
  pause's first STATE. Oracle fact (ActionScheduler.Accept): a stale ACTION (> 3 frames late) is dropped before
  EndLost and does NOT clear BrainLost; 015907's act.lost went false at 12361289 on run_episode's closing zero ACTION
  / input.release, after the loop had read the pause, so the loop's STATE was never one frame from a wrong cause (the
  verifier's reading); PauseWatch is insurance. The watchdog's 250 ms counts from the last ACTION received (stale
  ones too), its 6 frames from the last accepted.
- `AttemptRecord.start_resume`: the taps of the episode start's resume (the live check's episode_settings now shows
  them).
- 10-08 after 03:00 (1228 rows to 04:02): 4 more HARNESS_FAILs, all old code. 3 watchdog pauses that died exactly like
  015907 (time_scale 0.0, "not collecting"): 034416 i0 ep5 and 034525 i1 ep6 in the same second (03:48:02), 034808 i1
  ep0 (03:49:18); last ACTION 25 / 28 / 15 frames before the first paused STATE; no long planner decision logged
  (max 17 ms) and STATE latency up from 0.8 to 4-11 ms: a machine-level stall like 10-04 21:01:15, not a planner path.
  1 wave-start savestate timeout (031851 i3). pause_quit.md 11.1.
- `recovery_check`: worker_pause / worker_norecover run `combat_run.worker` itself on the probe's link (_Shared, no
  second connection), title_items maps the title's main menu (Down x1..4 + Enter, Up x1 + Enter: does it wrap?).
- Full suite (tree at f0dba93 minus comments): 1160 passed, 3 skipped, 1 xfailed, 1 failed = the known timing budget
  test_hitbox_tables::test_support_query_matches_reference_and_meets_the_budget (3.93 ms > 3 ms: run pinned to the
  E-cores at below-normal priority); it passes alone (2.5 s).
- Process safety (round 1, disclosed then): at ~01:00 PDT round 1 ran Stop-Process -Force on pids 32988 and 58000
  (sleep.exe), thinking 32988 was its own finished pytest; the pid had been reused, so another session's wait loop
  was probably killed. If a track's wait script vanished around 10-08 01:00, that is why. Rule followed since: stop
  only what this session started, through its STOP file or TaskStop, and check Win32_Process CreationDate /
  CommandLine before touching a pid. Round 2's dev left `tail -n +1 -f ...live_20261008_033740_i4.log` running (pid
  44972, started 03:37:44, parent 52292): harmless, not started by this session, left alone; its session should stop
  it.
- Live check NOT run this round: instance 4 has been locked by routes since 04:07 for a 4-hour Lace2 data collection
  (run 20261008_040729_Lace2_data, worker pid 51860, frozen C:\ssbot\live_rb4_2f74075, until ~08:07), and 0-3 are
  locked by diag / r6rules / r8. Waited 04:12 - 04:47, then stopped waiting (no lock was taken). Ready to run (frozen
  checkout C:\ssbot\live_recov_ef67b89, CODE_REV ef67b89, venv built; its code equals the branch head, later commits
  touch comments / docs / tests only), through the lock, about 5 min:
    cd C:\ssbot\live_recov_ef67b89\brain
    ..\scripts\uv.cmd run python -m ssbot.probes.recovery_check --instance 4 --cases worker_pause,worker_norecover,title_items,episode_settings,brain_lost
  It writes C:\ssbot\sandbox\recovery_check\<time>_i4.json (worker rows under recovery_check\worker_*). worker_pause /
  worker_norecover check the worker path live (rows: ep0 HARNESS_FAIL "paused unasked ... (a Pause key in the
  harness's own ACTION ...)", ep1 not HARNESS_FAIL with time_scale_game 1.0; the log shows "after the harness
  failure: ..." or "paused before the episode (...): unpaused"). title_items answers the open TITLE_ITEM question
  below. Afterwards instance 4 is in the sandbox slot / Bell Beast savestate: tell routes to reload its own state.

Next / open issues:
1. The watchdog pauses come from fight-loop stalls >= 250 ms; loop_gap_ms in the summaries will show where. Reducing
   them (planner warm-up, CPU sharing) is not done here. The latest (015907) was one 1.6 s planner decision on a
   path the warm-up did not cover (r5value code).
2. In data mode a watchdog pause could be resumed and the episode continued; it still ends HARNESS_FAIL (the policies
   and taps do not handle paused frames).
3. Keep the mouse off the training windows (it moves menu highlights, P7); the recovery now copes, but every
   MenuError costs a few seconds.
4. load_slot after Esc back from a title sub-menu always pays one MenuError (the highlight stays on the item it came
   from); an Up before the Enter would save ~6 s but needs each sub-menu's menuState mapped to its main-menu item.
5. recovery.TITLE_ITEM (Up count after a MenuError) assumes the main menu lists Start Game / Options / Achievements /
   Extras / Quit and only Options (Up x1) is verified live. If the list does not wrap, Up x4 always reaches Start
   Game and is the robust choice; if it wraps and an item is hidden, the count overshoots and the same MenuError can
   repeat until SLOT_TRIES (3) runs out (no setting is changed). The live case title_items measures both; change
   _unstick after it, not before.
6. The live re-check of this round's worker path (worker_pause / worker_norecover) is pending (see above); the unit
   tests cover it on the stand-in game.

## Task R5 model - Forum plan round R5, the behaviour-model half (branch worktree-wf_814dfeea-b10-1)

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_814dfeea-b10-1`, branch `worktree-wf_814dfeea-b10-1` (from main
bc46dc9). Offline only (no game instance touched, no seeds). Facts: `docs/facts/1.0.30000/forum.md` section 18 (Chinese;
the R5 value track's section is 17).
Large outputs (not in git): `C:\ssbot\data\m2_forum_r5m\` (decision records `recs_dev.pkl` / `recs_test.pkl`, hero silk
side caches `hero\`, `study_dev.json`, `holdout_test.json`, `summary.md`, `tiny_orbit_report.json`, `branch_gap.json`,
`pipeline_v2.cmd`, `val_run.cmd` and the validation logs). Frozen checkout of the validation: `C:\ssbot\live_r5m_092e3e2`.

### Done (committed)

- **Sensing time from the FSM statics** (`combat/branch_model.SENSING`, forum.md 18.1): for every Forum decision state
  what its Control FSM reads (trigger ranges every frame / once at entry, GetDistance, stored angles, the hero's silk,
  SendRandomEventV4 counters) and when: "branch" (the exit frame is the sensing frame), "entry" (Choristor Hop Antic,
  Clawmaiden Spin Antic, Clapper Evade Scuttle, Minister Retreat?'s coin, Maestro Slash Recover), "stored:<state>"
  (the Reed's throw: Throw Antic Anim stores aiming-up, Throw Aim stores the angle read 0.4 s later). V4 semantics read
  from the decompiled source (eventMax / missedMax). Trigger shapes `RANGES` (scene bundle AlertRanges, mirrored with
  flipX), `geometry()` / `in_range()`.
- **Cooldowns and branch-split history as view-legal covariates** (`BranchMemory`, fed by Control entries and hits):
  gates (Bellbearer Evade Cooldown + can_evade, Reed armed / Just Did Defend, Clapper Evaded, Envoy Charge Range +
  Alerted; the Envoy gate was wrong in round 1, see the fixer round below),
  counters / timers (Choristor hops + last hop, Clawmaiden suck timer age, Maestro dead Tinies), anti-repeat history
  of each decision state (last / last two choices, run, decisions since each outcome = the V4 counters), the previous
  attack and its last state (`prev_end`: defend not hit vs countered), time since it ended, where the state was
  entered from, the last hit seen (round 1 excluded a same-frame hit as "the TOOK DAMAGE cause": wrong, the
  exit follows its hit by 12-18 frames when at all; fixer round), Clapper buddy facts, the hero's silk.
- **Study and product** (`knowledge/forum_branch.py`, `tools/forum_branch scan|study|build`): one record per exit of a
  decision state with geometry at 8 timings (branch, entry, stored, lead 0.1-0.5 s); per decision a greedy forward
  selection by 2-fold (by fight) CV log loss over geometry at each timing + history, backoff tables
  (`DecisionModel`); the best timing kept. `knowledge/1.0.30000/enemies/forum/branch_model.json` (61 decisions, fit
  on all 142 DEV fights).
- **Runtime** (scoring only): `EnemyTracker.mem` (one line each in `enter` / `_hit`), `MultiForecaster(branch=...)`
  -> `BranchView` (hero box / silk and enemy positions kept 1 s so a decision's geometry is taken at its timing;
  **round 1 did not compute 26 decisions' selected covariates at runtime: train / serve skew, fixed and checked
  frame by frame in the fixer round**),
  `branch_probs(iid)`, `next_attack_probs(iid)`, `Subject.next_p`; `ForumPlannerPolicy(branch_model=True)` switches
  it on (default off: nothing in the planner consumes it yet; the R5 value / R6 O and BAIT are the consumers).
  `multi_recall --branch` runs the recall with it on.
- **Body-entry reactive branches** (`branch_model.REACTIVE`, `BranchView.reactive` / `entry_prob`): Bellbearer evade
  0.97, Clapper evade (coin) 0.49, Reed evade 0.95 / defend (coin) 0.45 with gates from BranchMemory and the revealed
  coin (in the box with the gate open for 2+ frames and no reaction -> 0 for the visit); `entry_prob` gives the first
  gate-open entry of a candidate's hero-box path. J / P only.
- **Tiny one by one** (`combat/tiny_orbit.py`, `tools/tiny_orbit`, `knowledge/.../tiny_orbit.json`): defend orbit
  around Maestro + (0, -0.22), radius schedule by defend age, measured angular rate +-216 deg/s with the sign following
  the Maestro's flipX, clamped to the terrain bounds; charge facts measured (below).
- Tests: `tests/test_branch_model.py` 19 (gates, hops / suck age / same-frame hit, backoff, shapes and mirroring, the
  SENSING table, orbit sign and clamp, greedy on synthetic data, reactive gates and the revealed coin, and the
  scoring-only check: occupancy, probability map and support set identical with / without the branch model on the
  synthetic Reed, next_p filled only in decisions).

### Measured (forum.md 18.3-18.8)

- **Held-out log loss** (nats / decision, weighted; **round 1, superseded by the fixer round**: the fire-frame model,
  P(successor | the decision fires now), on offline features the runtime did not compute; it is not a forecast
  mid-state): DEV 142 fights (2-fold CV) unconditional 0.740, R0 conditioners refit 0.539, new 0.332; TEST 202 R1
  fights: 0.695 / 0.512 / 0.315; ECE 0.018 -> 0.009. Largest gains: trigger-shape decisions become near deterministic (Clapper After
  Scuttle / Dmg Attack / Walk, Choristor Hop Antic at its entry, Slash Check), Bellbearer In Range 1.06 -> 0.11,
  Clawmaiden Fly 1.16 -> 0.31 and Spin Antic 1.10 -> 0.59 (hero silk at entry), Reed Alert 1.43 -> 0.39, Minister
  Chase 0.52 -> 0.20. Worse than R0: Maestro Attack Choice (0.318 -> 0.331), Clapper Escape Jump on TEST (0.290 ->
  0.302); small-n calibration worse: Envoy Charge, Reed Throw Up (overfit, 4 covariates on 311).
- **Timing** (61 decisions): branch frame 45, entry 3, stored 4, fixed lead 9 (clear only for Clawmaiden Spin 1 / 2:
  the silk is already taken at the branch frame, Tiny Pull Up 0.3 s, Reed Throw Lock = the Throw Aim facing; the rest
  within 0.005-0.02 nats of the branch frame). Geometry alone confirms the FSM: Hop Antic branch 0.081 vs entry 0.006;
  Throwing Up? 0.245 vs stored 0.069; every-frame decisions degrade with any lead (Dmg Attack 0.006 -> 0.169 at 0.1 s).
- **Defend branches** (time to the next attack, p50): Minister not hit 0.97 s vs countered 1.11 s (same next-move
  mix); Reed not hit 0.67 s, counter missed 0.80 s, counter hooked 1.10 s (fewer evades); Bellbearer after an evade
  the next attack is a throw 2,229 / 2,229; Maestro never defends twice.
- **Tiny**: settled orbit (>= 1 s into the defend) held-out error p50 0.33 / 0.67 / 1.32 / 2.54 u at 0.1 / 0.2 / 0.4 /
  0.8 s but p99 4.0-9.9 and max 20-28 u (terrain blocks the low half of the orbit, hits, Maestro motion): fine for
  scoring, **not** a support replacement. Charge: FIRE READY -> Fire 0.717 s (p1 0.692, p99 0.733), about 52 deg
  down, toward the hero's side 99.7 %, the pick is random (nearest-to-hero 3,050 vs 3,042 expected); a standing hero
  is hit 0.8-0.9 % 2-8 u behind the Maestro, 7.1 % right under it, 31 % / 56 % / ~59 % at 3 / 6 / 8-10 u in front.
- **Cost** of next_p for every enemy in a decision (full gauntlet replay, 51,823 frames): p50 0.17 ms, p99 1.05 ms,
  max 7.8 ms per frame -> off by default.
- Validation (frozen 092e3e2): recall with the branch model ON (`multi_recall fresh --tables 0 --branch`, R0's 35 fresh fights): L2 / L3 / L4 74,585 / 74,585 each, all by the forecast, hooks 465 / 465, identical to the R3 certification (2a10a0d, fresh/tables0). Bell Beast wrap (`multi_recall bellbeast` i4_000 + 20261004_095304 i0_001, 4,001 frames each): 0 differences in all eight checks (boss mode has no BranchView: this checks the branch-off path, which is what the regression rule asks for, not the branch model). Full pytest at 092e3e2: 1,146 passed, 3 skipped, 1 xfailed (15 planner / kinematics tests first failed only because the run's NUMBA_NUM_THREADS was 3; rerun with 4: 73 / 73); the later commits' tests/test_branch_model.py 19 / 19.

### Next / open issues

1. Consumers: the R5 value track's O / BAIT and R6's targets should read `Subject.next_p` / `branch_probs` (timing
   via `BranchModel.timing`) and `BranchView.entry_prob` for the reactive branch; switch `branch_model=True` in the
   policy then and re-measure the tick cost (cache the per-frame geometry first if p99 matters).
2. The walk's own placement probabilities (`MultiForecast.prob`) still come from the unconditional p_succ; a per-subject
   rescale of the next instance's rows by `next_p` is the obvious next step (scoring only, needs an A/B).
3. Tiny: a follower model (defense point + terrain block + speed cap) and a fresh certification before the per-fly
   orbit can replace the R2 cluster union in the support.
4. Small-n decisions: cap the covariates by n (Envoy Charge, Reed Throw Up, Escape Jump); hidden V4 counters (e.g.
   Minister Evade? out of range) could be filtered as a hidden state instead of approximated by the visible history.
5. The Tiny's Control FSM is in a bundle outside the scene (Maestro CreateObject ext:45): not decoded.
6. Integration: the R5 value track (worktree-wf_814dfeea-b10-2) also appends a forum.md section after 16 (its 17;
   this one is 18) and both tracks touch combat/enemy_tracker.py and multi_forecast.py: expect textual merge
   conflicts there (this track adds EnemyTracker.mem, MultiForecaster(branch=...), Subject.next_p). The two
   sessions share one scratchpad directory (a file of this track was overwritten): keep run scripts in
   C:\ssbot\data\m2_forum_r5m.

### Fixer round (week push round 2, 2026-10-08; code 2f5b96a -> dd5cbff, offline, no game instance)

The round-1 verifier refuted three claims: that `MultiForecaster(branch=...)` fills `Subject.next_p` with the model
scored at 0.315 (train / serve skew), that 0.695 -> 0.315 is a forecasting gain (the model was fit on fire frames
only), and that the Envoy Charge Range gate is modelled faithfully. Its findings were 2 high, 1 medium and 4 low; all
are addressed. Outputs are in `C:\ssbot\data\m2_forum_r5m\fix\`: `v_2f5b96a\` (rescan, studies, build, `holdout_test.json`,
`tables.md`, `gates_check.txt`) and `val_7db1c2d\` (parity, recall, Bell Beast, tests). The facts are in forum.md
§18.11; §18.2-18.4 and §18.8-18.10 were corrected in place.

- **Train / serve skew (high).** The runtime and the scan now compute every covariate with the same functions:
  - the R0-era geometry goes in `geometry()`: `dist_visible`, `last_seen_x`, `hero_x` (`side_visible` is `side`);
  - `since_<family>` ("none" before the family's first attack) and `miss_<outcome>` go in `BranchMemory.features`;
  - `clapper_context`, and `TinyOwners`, which assigns owners online from past frames only (the scan's whole-fight
    vote is gone);
  - the scan's segmentation is used at runtime too: the walk's TypeTable lacks MA_POINT and the Envoy's
    EN_HOPSLASH / EN_ENTRY, so `prev` / `run` / `since_*` differed. The model now stores it (`branch_model.json`
    "segmentation", written by build from FORUM_SPECS, read by `memory_for_table(tt, model)`), because
    `test_import_firewall` forbids combat -> knowledge.gauntlet_tables;
  - the hero transform (`pos_transform`), where round 1 used the hurtbox centre;
  - enemy rows only on frames the enemy was seen, at most 0.25 s old;
  - entry / stored geometry from a snapshot taken at each state entry.

  The scan walks frames the way the runtime does: a frame's events, then the frame's end. A new check,
  `forum_branch parity`, replays a cached fight's recording through OracleBackend -> MultiForecaster(branch=...). On
  every frame an enemy is in a modelled decision state, it compares BranchView's covariates with the scan's: geometry
  at now / entry / stored, all history, gates and context. Over 7 fights (3 R0 DEV, 4 R1 TEST), **705,805 rows
  matched with 0 differences**. Test: `test_runtime_covariates_equal_the_scans_on_a_recording` (skipped when the
  recording or the forum hitbox npz is missing).
- **Fire-frame-only fitting (high).** The `types` tables remain the fire-frame model, now documented as P(successor |
  it decides now); `branch_probs` defaults to them. A new set of forecast tables, `ahead`, is fitted on samples taken
  every 0.1 s of every visit to a decision state (0.25 s for the Tiny; the Tiny's Dead is skipped), each labelled with
  how the visit ended. The greedy selection is the same; 29 states have a table. `next_attack_probs` / `Subject.next_p`
  use them for the current state, then for chained decisions as if entered now; instant decisions keep the
  fire-frame table. On the 889,333 TEST samples (the frames the planner queries), in nats per sample:

  | Samples | Per-visit p_succ | Per-sample unconditional | Fire-frame model, queried mid-state | Forecast |
  |---|---|---|---|---|
  | All | 0.716 | 0.603 | 4.99 | **0.581** |
  | 0.2-0.3 s before the exit | 0.639 | - | 4.38 | **0.427** |
  | 0.5-0.6 s before the exit | 0.767 | - | 5.36 | **0.576** |

  The fire-frame column covers only the 849,049 samples where that model can be queried (0.596 for the forecast on
  that subset). Of the 0.135 nats gained over the per-visit table, 0.113 comes from the time-weighted marginal
  alone; all the covariates together (`age`, geometry, history) add only 0.022, because mid-state the next move
  depends on where the hero goes next.
- **Envoy gate (medium).** Charge Range is active at scene load. It arms once a Walker visit reaches 1.5 s and stays
  armed after Walker is left (ActivateGameObjectDelay with resetOnExit 0). Slash Antic turns it on, Charge Antic off,
  and a new `alerted` gate is added. After the rescan, every Walker -> Charge Antic has both gates open: DEV 465 / 465,
  TEST 104 / 104 (round 1 had 131 / 34 with the gate shut). Test: `test_envoy_charge_range_gate_follows_the_fsm`.
- **Lows.**
  - The same-frame hit exclusion is dropped. It applied to 1 of 1,100 TOOK DAMAGE exits. About a third of the
    Clapper / Minister exits follow a recorded hit by 12-18 frames; the rest have no recorded hit within 0.35 s.
    The docs are corrected.
  - The "R0" baseline is renamed "R0 conditioners refit" (`r0_refit`): it was never the shipped tables.
  - The hero reference point and the Tiny owner are fixed (see above).
- **Rebuilt `branch_model.json`** (schema 2, 243 KB). Fire-frame log loss on runtime-computable covariates: TEST 0.695
  -> **0.284**, DEV CV 0.740 -> 0.279, against 0.511 for the R0 refit. `age` (time in the state) is selected by 25
  decisions. Timings chosen: branch 45, entry 1, stored 3, lead 12; Hop Antic and Evade Scuttle now use `age` at the
  branch frame.
- **Re-measured.**
  - Gates: 0 violations for the Bellbearer cooldown, Reed armed / jdd and Clapper evaded. The Maestro never defends
    twice: DEV 4,412 / 4,412, TEST 3,172 / 3,172.
  - Geometry-only sensing times are unchanged: Hop Antic 0.081 at the branch frame vs 0.006 at entry; Throwing Up?
    0.245 vs 0.069 at the stored time.
- **Validation** (recall, Bell Beast and the 7-fight parity: frozen `C:\ssbot\live_r5mf_7db1c2d`; full pytest and a
  2-fight full parity: `C:\ssbot\live_r5mf_dd5cbff`, which only moved the segmentation into the model):
  - parity: 0 differences (above);
  - cost of next_p for every living enemy per frame, on the round-1 fight (20261003_074719 i3 ep0, 51,823 frames):
    p50 0.13 / p99 1.07 / max 5.0 ms at 7db1c2d, 0.11 / 0.80 / 3.1 at dd5cbff with less load (round 1: 0.17 / 1.05 / 7.8);
  - parity again at dd5cbff, 2 full fights: 331,979 rows, 0 differences;
  - recall with the new model on (`multi_recall fresh --tables 0 --branch`, R0's 35 fresh fights): identical to round 1
    (092e3e2) and the R3 certification, including L2-L4 74,585 / 74,585 and hooks 465 / 465;
  - Bell Beast wraps: i4_000 and 20261004_095304 i0_001, 4,001 frames each, 0 differences in all eight checks (the
    branch-off path);
  - full pytest at dd5cbff: 1,150 passed, 2 skipped, 1 xfailed. The 7db1c2d run had one failure,
    `test_import_firewall` (combat -> knowledge.gauntlet_tables -> ipc); that is why the segmentation moved into the model.

Open issues (fixer round):
1. **Tiny Ready's forecast does not transfer.** TEST log loss is 1.19 against 0.98 for the per-visit table, although
   DEV CV was 0.77. Its exits are the Maestro's choices. Consumers should not trust `next_p` for a Tiny in Ready, or
   should condition it on the Maestro's state.
2. **Small-n fire-frame decisions are unstable on TEST.** Clawmaiden Spin 1 scores 0.412 against 0.188 unconditional;
   Spin 0 is also affected. Envoy Charge scores 0.909 against 0.760 for the R0 refit, and Reed Throw Up is unstable
   too. Capping covariates by n is still not done.
3. **The forecast is averaged over the data policies' hero motion.** A forecast conditioned on a candidate (the
   fire-frame model times a per-frame hazard along the candidate's hero path) is not built. R5 value / R6 consumers
   asking "what if the hero goes there" should use `branch_probs` (fire-frame) at the candidate's frames plus their
   own timing.
4. **Nothing in the planner reads `next_p` yet.** `ForumPlannerPolicy(branch_model=True)` is still off, and the
   forecast tables have never run live.
5. **Integration.** This branch also touches `combat/multi_forecast.py` / `enemy_tracker.py`, as R5 value does. The
   forum.md section is 18; R5 value's is 17.

## Task R5 value - Forum plan round R5, the terminal-value half (branch worktree-wf_814dfeea-b10-2)

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_814dfeea-b10-2` (from main bc46dc9). Facts: forum.md section 17
(Chinese); plan R5 row: the 2026-10-08 note. Frozen checkout `C:\ssbot\live_r5v_35e5fe6` (git archive of 35e5fe6 +
CODE_REV + the R3 tables from `C:\ssbot\tables\forum_r3_2a10a0d`); outputs `C:\ssbot\data\m2_forum_r5v\`.

### Done (committed)

- `combat/terminal.py`: the plan's support field (`EnemyFields.build`: per owner, 0.5 x 1 u cells x 0.1 s bins from
  0.6 s to the forecast horizon, the store's per-bin bounding boxes over every entry a placement allows in the bin,
  tubes / boxes / paths hulled over the bin and dilated by the hurtbox; conservative: field empty => fine empty), the
  body field (`from_bodies`, what J uses: see below), reachable templates (`forum_reach.npz`, 4 end classes x
  0.2 / 0.5 / 0.9 / 1.4 s from 135 primitives of the Forum kinematics; rebuild: `python -m ssbot.combat.terminal`),
  `TerminalValue.rows` (E, trapped, overlap, H_exp per row, numba), `kill_value` (leave-one-out near the hero / hits
  needed).
- ForumPlanner: `ForumConfig.terminal` (env `SSBOT_FORUM_TV`; default on in rounds 1-2, off since round 3) adds w_E E - w_trap trapped - w_ov overlap -
  w_H H_W[h] H_exp to J and multiplies each target's hit weight by (1 + w_K kill value); `ForumConfig.T` from
  `SSBOT_FORUM_T` (default 36; the policy's PlannerConfig follows it). Scores only (test: Hz, U and FORCED_RISK equal
  with and without, deterministic mode).
- Hit-target fix (a bug since R3): `EnemyTracker.body` was the bounding box of every enabled collider incl. the range
  triggers (layer 13: Envoy 108 u, Choristor 30 u, Reed 24 u wide), so every swing "hit". New oracle-only
  `Entity.hit_polys` (enabled colliders not on layers 13 / 14 / 27), used by EnemyTracker for the body (env
  `SSBOT_FORUM_HITBODY=0`: the old targets). The support does not read `body` (unchanged, certification stands).
- Policy: stats `tv_ms_p50/p99` and `terminal` (chosen rows' E / trapped / overlap / H_exp), decision log `fi.tv`;
  `forum_policy_replay` prints them.
- Tests: `tests/test_terminal.py` (8); test_forum_planner + test_multi_forecast + test_worldstate + test_observability +
  forum tactics / policy hits pass.

### Measured (forum.md 17)

- Support field saturation (A0b recording 20261005_205437 i1 ep0, wave 0): the union is 100 % of the cells in every
  bin 0.6-2.0 s at every sampled tick, each of Reed / Envoy / Choristor alone 100 %; the fine query covers the whole
  floor row from t = 0 (bounding-box rows of later RE_STAB / RE_THROW / EN_CHARGE instances, entry 0.02-0.1 s, 50-93 u
  wide). Probability weighting does not help (p = 1 rows: current-instance windows, CH_IDLE bbox 92 u, arena boxes).
  So the plan's E / trapped from the support carry no information in wave 0; also a structural cause of the 87 %
  FORCED_RISK. Field build p50 1.5-2.0 / p99 3.3-4.1 ms; 0 violations of "empty => fine empty" (synthetic test; on the
  recording 967,492 empty committed-field points, the full field had no empty cell).
- Body field + terms: see forum.md 17.3 / 17.4 (replay table: tick p50 / p99, tv cost, chosen rows' E / trapped).
- Terminal value cost (A0b replay i1 ep3, heavy load, offsets per cell, 35e5fe6): p50 1.30 / p99 3.65 ms per tick
  (before the per-cell offsets 1.65 / 4.52); tick p50 13.7 ms in every config at that load (A0 live 7.4 ms).
- Bell Beast (Forum switch off): `planner_bench` on 20261003_144536 i4_000, 3000 frames, main bc46dc9 (frozen
  `C:\ssbot\live_main_bc46dc9`) vs 35e5fe6: every non-timing output equal (2,951 ticks, FORCED_RISK share 0.0285);
  by construction the Bell Beast path reads neither `hit_polys` nor combat.terminal. Full test suite passed (tests +
  ssbot/tests). The 50-episode Bell Beast batch is the integration step's.

### Round 1 stop (2026-10-08 01:23 PDT, weekly usage 100 %) and the overnight A/B

The armed driver `C:\ssbot\sandbox\r5v_ab.ps1` (frozen `C:\ssbot\live_r5v_35e5fe6`) ran on instance 0 01:59-02:33
and released the lock: TV 26 (`20261008_015907` 1 HARNESS_FAIL + `015959` 25), HB 25 (`021002`), T48 25 (`022115`).
Report: forum.md 17.5 (all QUIT in wave 0, no arm changed the outcome).

### Round 2 (2026-10-08 03:00-, after the weekly reset)

Merged main (already up to date at bc46dc9). Commits from f7b6217 on.

Done (committed):
- forum.md 17.5: the overnight A/B (`forum_a0_report`): every episode a Q1 QUIT in wave 0; hits / episode 4.0 (TV) /
  4.16 (HB) / 4.4 (T48) vs 4.27 (A0b); hits / min 18.4 / 18.4 / 16.6 vs 19.1 (bootstrap CIs overlap); support-outside
  hits 0; FORCED_RISK 0.82 / 0.81 / 0.89 vs 0.80; hit sources moved from the Envoy to the Choristor (target fix).
- Why (forum.md 17.7): `ForumPlanner.last_sel` (the selection's inputs by reference), `ForumConfig.p_all` (audits:
  FORCED_RISK P / first contact for every row, choice unchanged) and `tools/forum_tv_audit` (open-loop replay; per
  tick the deciding key, rankings, hindsight-clear rows against the recording's threat colliders, per-key AUC;
  `--dump` per-tick rows, `--merge`). On 25 TV-arm episodes + 9 A0b ones: in FORCED_RISK (3/4 of EVADE ticks) P = 1
  and the first contacts tie, their AUC is exactly 0.5, so J decides 83 % / 75 % of the picks; the terminal value
  changes 18-25 % of the picks but the pick is clear in hindsight only ~1 point more often (68.4 vs 67.4 %; before
  hits 30.4 vs 27.8 %): the body field is weakly informative (AUC 0.60-0.65 on the TV recordings, ~0.55 on A0b) and
  rides on J0's target terms (AUC 0.46 before hits). R5 model's next_p not used (the verifier's verdict; not merged).
- `ForumConfig.commit_rank` (737048f, default on since 3797b3e, `SSBOT_FORUM_PC=0` off; forum.md 17.8): after P, the
  share of stage 1's frames in contact with the committed support (P_cm) then with the current attacks' fine
  placements (P_f); they lead the p_k preselection too. Offline (same ticks): picks clear in hindsight 74.3 / 70.9 %
  (+5.9 / +6.0 points), before hits 41.5 / 42.3 % (+11 / +10). Plan p50 +0.7-1.6 ms (open-loop replay). Test
  `test_commit_rank_refines_forced_risk_by_the_committed_support`; off = bit-identical (the added keys are all 0).
- Plan R5 row: the 2026-10-08 round-2 note.

Diag track (wave-0 forensics, worktree-wf_fa16f06f-127-8, HANDOFF "Task wave-0 forensics") found the same cause
independently (support saturates, the pick falls to J, "J-greedy") and built `forced_rank = "seen"`
(`SSBOT_FORUM_FR=seen`: contact with the damage colliders seen now, moved along their velocity, BEFORE the share).
Same ticks (forum.md 17.8): seen alone 71.8 / 71.7 % clear (before hits 37.5 / 41.7 %), commit_rank alone 74.3 / 70.9
(41.5 / 42.3), **stacked seen > P > P_cm > P_f 78.7 / 76.3 (48.7 / 51.0)**, live 68.4 / 64.9 (30.4 / 32.7). So
8617aa6 ports diag's planner part of 3608489 verbatim (seen_contacts, seen_polys, warm_kernels, SSBOT_FORUM_FR, its
tests; the policy's `_fcfg`) and stacks commit_rank after it. **Merge note**: this branch and diag's both change the
FORCED_RISK block of `combat/forum_planner.py` and the policy's planner construction; this branch's version is the
superset (diag's key first, then P, P_cm, P_f), so take it when the hunks conflict (diag's later commits up to
b4345c6 touch only its tools and HANDOFF).

Round-2 A/B (instance 0, 04:20-05:18, frozen `C:\ssbot\live_r5v2_8617aa6`, driver `C:\ssbot\sandbox\r5v_ab2.ps1`,
lock released; forum.md 17.10), A0b protocol, TV on, T 36. CORRECTION (round 3, verifier): the arms were NOT
interleaved; they ran as sequential batches (SPC 04:20-04:37, PC 04:37-04:51, control 04:51-05:03, SPC 05:03-05:18)
under very different machine load, so the tick / late columns are each batch's load, not the code's cost:

| arm | runs (20261008_) | episodes | hits / min (95 %) | time alive p50 / mean (s) | FORCED_RISK | tick p50 / p99 | late |
|---|---|---|---|---|---|---|---|
| TV control (both off) | 045158 | 25 | 19.0 (17.1-21.0) | 12.4 / 13.7 | 0.813 | 9.8 / 19.0 | 3.5 % |
| PC (commit_rank) | 043725 | 25 | 12.4 (11.3-13.7) | 21.4 / 21.3 | 0.885 | 12.8 / 21.2 | 17.6 % |
| SPC (seen + commit_rank) | 042011 + 042143 + 050303 | 50 | 10.3 (9.5-11.3) | 23.5 / 24.4 | 0.915 | 12.0 / 20.2 | 40.1 % / 5.8 % (two batches) |

Every episode is still a Q1 QUIT in wave 0 (about 4.2-4.4 hits), 0 WOULD_DIE, 0 kills, 0 support-outside hits, the
envelope audit clean: the hero survives 55-78 % longer per hit but never kills; the next bottleneck is offence
(R6 / R8). commit_rank is now on by default (3797b3e, `SSBOT_FORUM_PC=0` off); "seen" stays diag's switch (default
share). (Superseded by round 3 below: "recommend both on" rested on offline results only, and the "late ticks 18-24 %
= the code's cost" reading was load; the paired cost is in round 3.)

### Round 3 (fixer, 2026-10-08 06:00-; verifier findings on ec39281; forum.md 17.11)

Done (committed):
- 2ef6383 `MultiForecast.occupied_split`: stage 1's support query split by the placements' committed flag (union
  bit-identical to `occupied()`, the committed part = `_union_occ(committed_only=True)`, the fine part = `_fine_occ()`);
  ForumPlanner takes P_cm / P_f from it when commit_rank is on (no second query after the envelope; stage 1 is inside
  the envelope's deadline budget). Keys bit-identical to the old ones (tests + 1,907 real FORCED_RISK ticks).
- 2ef6383 terminal value off by default (`SSBOT_FORUM_TV=1` on): no closed-loop gain (18.41 vs 18.42 hits / min),
  ~1 point offline, 0.9-1.3 ms before the envelope.
- 2ef6383 `SSBOT_FORUM_AB="name:pc=0|1,fr=share|seen;..."`: ForumPlannerPolicy switches the arm per episode (episode k
  runs arm k mod n; `policy.ab_arm` in attempts), so arms share the load inside one batch.
- b96559f forum.md 17.7 / 17.8 / 17.10 corrections: random-row baseline for the hindsight shares (before hits:
  commit_rank +4.7 / +3.2 points over a random allowed row, seen +0.7 / +2.5, stacked +11.9 / +11.9; the live pick is
  6.6 / 7.4 points BELOW random there: selection bias, the recorded path is what the threats aimed at); J0's AUC 0.46
  is path correlation, not "reversed"; the round-2 arms ran in sequential batches and their late ticks were load
  (same SPC code 40.1 % vs 5.8 %). `forum_tv_audit` reports `clear.random`. Plan R5 row note corrected.
- Paired cost (`C:\ssbot\data\m2_forum_r5v\round3\pc_bench.py`: one process, one policy per arm, every STATE to every
  arm in rotating order): commit_rank +0.25-0.4 ms plan p50 (the old second queries 0.6-0.9 / 2.7-4.8 ms p50 / p99),
  seen 0.09-0.12 / 0.4-1.0 ms; late ticks equal within noise (wave 0: C 3.0 %, PC 2.6 %, S 2.9 %, SPC 2.4 %).

Round-3 A/B (done, lock released 07:26; driver `C:\ssbot\sandbox\r5v_ab3.ps1`, frozen `C:\ssbot\live_r5v3_2ef6383`,
instance 0, A0b protocol, terminal value off, T 36): run `20261008_063420` (seed 300900; the first batch 300800 was a
"paused unasked" HARNESS_FAIL on its first episode), 100 episodes, arms C / PC / S / SPC switched PER EPISODE in one
batch (same load: 1.4 % late overall). Report `C:\ssbot\data\m2_forum_r5v\round3\ab3_report.txt` (forum.md 17.11):

| arm | hits / min (95 %) | time alive p50 / mean (s) | FORCED_RISK | plan p50 (ms) | late | kills |
|---|---|---|---|---|---|---|
| C (both off) | 18.9 (17.1-20.8) | 12.7 / 13.2 | 0.808 | 4.11 | 1.9 % | 0 |
| PC (commit_rank) | 13.7 (12.5-15.2) | 19.6 / 19.7 | 0.863 | 4.49 | 1.3 % | 0 |
| S (seen) | 13.8 (12.5-15.3) | 16.9 / 18.3 | 0.879 | 4.29 | 1.3 % | 1 (Envoy) |
| SPC (seen + commit_rank) | 10.2 (9.1-11.6) | 27.0 / 26.1 | 0.910 | 4.61 | 1.3 % | 1 (Choristor) |

Ratios (bootstrap): PC / C 0.72 (0.63-0.83), S / C 0.73 (0.64-0.84), **SPC / S 0.74 (0.64-0.87)**, SPC / PC 0.75;
main effects commit_rank 0.73, seen 0.74, no interaction. So commit_rank helps on top of seen in a paired live test
(round 2 had only offline evidence), and the late ticks do not grow under the same load. Still every episode a Q1
QUIT in wave 0, 0 WOULD_DIE; the track's first kills (one Envoy, one Choristor). Diag's paired seen vs seen_cf
(340100-340124, recomputed with `ab3_report.py`, `round3\diag_pair_report.txt`): 12.4 vs 9.4, ratio 0.76 - the same
effect as SPC / S; seen_cf (seen, then the committed fine placements' share) and SPC (seen > P > P_cm > P_f) are
near-identical mechanisms; seen_cf pays a second fine query after the envelope (plan p50 5.06 vs 4.35 in its pair),
SPC gets its keys from stage 1's split (4.61 vs 4.29).

Tests (code 2ef6383 + b96559f): full suite 1,143 passed, 2 skipped, 1 xfailed
(`C:\ssbot\data\m2_forum_r5v\round3\fullsuite3.txt`; the runner wrote it over round 2's `fullsuite2.txt` first, so the
round-2 file now holds this run). New tests: `test_occupied_split_is_the_union_and_its_committed_and_fine_parts`,
`test_ab_arms_switch_per_episode`; the commit_rank test now checks the keys against the old second queries. Bell
Beast: untouched (MultiForecast gained a method nothing on its path calls; ForumPlanner / ForumPlannerPolicy only).

### Needs deploy

- Nothing (no oracle change).

### Next / open issues

1. Integration: merge this branch with diag's (worktree-wf_fa16f06f-127-8): both change the FORCED_RISK block of
   `combat/forum_planner.py` and the policy's planner construction. This branch: seen > P > P_cm > P_f (commit_rank,
   keys from `occupied_split`), `SSBOT_FORUM_AB`; diag's later 82e94fa adds `seen_cf` (seen, then the committed fine
   share, a second query). Live, paired within each track, they are equivalent (SPC / S 0.74, seen_cf / seen 0.76;
   10.2 vs 9.4 hits / min in different windows): keep one. If seen_cf is kept, take its key from `occupied_split`
   (the committed fine part is `com` before the windows are or'ed in: expose it) instead of the second query. Both
   tracks' paired data support turning the seen key on by default at integration; the 50-episode Bell Beast batch
   is the integrator's.
2. Compute: done in round 3 (P_cm / P_f from stage 1's split query: +0.25-0.4 ms plan p50 for commit_rank, the old
   second queries alone were 0.6-0.9 / 2.7-4.8 ms p50 / p99; no late-tick difference under the same load).
3. The remaining gap (forum.md 17.9): 68-79 % of the stacked ranking's misses have a clear row tied on every risk key;
   the hits come from attacks not started yet (the saturated later-instance boxes): time-resolved later-instance
   placements (R2 / R3, recertify) or lead-time branch probabilities (R5 model's next step).
4. Wave 0 is still never cleared (2 kills in the 277 live episodes of this track, both in round 3's seen arms):
   offence (R6 targets, R8 clash) is next.
5. Terminal value: off by default since round 3 (`SSBOT_FORUM_TV=1` on); weights / body-field radius hand-set; in wave
   0 it is not the bottleneck (17.7). Kill value untested in closed loop.
6. Main's working copy has no `knowledge/1.0.30000/enemies/forum/*_hitboxes.npz` (git-ignored); this worktree's copy
   (= `C:\ssbot\tables\forum_r3_2a10a0d`) was used for the frozen checkouts.
7. Frozen checkouts `C:\ssbot\live_r5v_35e5fe6`, `C:\ssbot\live_r5v2_737048f` (unused), `C:\ssbot\live_r5v2_8617aa6`
   and `C:\ssbot\live_r5v3_2ef6383` can go; audit dumps (~60 MB each set) in `C:\ssbot\data\m2_forum_r5v\round2\` can
   go after integration.
8. Tests: full suite at 737048f 1,138 passed, 2 skipped, 1 xfailed; after the port and the default flip the Forum /
   planner / terminal / multi_forecast / worldstate / observability subset 224 passed; full suite (code of 3797b3e):
   1,141 passed, 2 skipped, 1 xfailed; round 3 (code of 2ef6383 + b96559f): 1,143 passed, 2 skipped, 1 xfailed
   (`C:\ssbot\data\m2_forum_r5v\round3\fullsuite3.txt`). Bell Beast: untouched by construction (ForumPlanner /
   ForumPlannerPolicy only, plus a new MultiForecast method); its equivalence tests are in the suite.
9. The "paused unasked" HARNESS_FAIL after a real quit ended a batch on its first episode again (seed 300800); the
   drivers work around it with a new seed, the fix is the harness's.
10. Hindsight audits (`forum_tv_audit`) are biased toward unexecuted rows: compare rankings against `clear.random`,
    not against the live pick (forum.md 17.11 item 3).

## Task R6 v0 - the person's rules as an L2 target layer + the Clapper controller (branch worktree-wf_814dfeea-b10-3)

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_814dfeea-b10-3` (from main bc46dc9), track r6rules (instance 1
after the route-boss collection; seeds 310000-319999). Facts: `docs/facts/1.0.30000/forum.md` section 17 (Chinese);
plan R6 row: the dated note of 2026-10-08. Stopped early on the weekly quota (99 % rule): the code and the offline
checks are done, the live A/B is queued on a detached driver (below). Round 2 (same branch): the A/B's result,
target holding, the Clapper controller live on wave starts, a full-gauntlet re-run (section "Round 2" below). Round 3:
the verifier's findings on ba7dddb, fixes and interleaved live re-runs (section "Round 3" below).

### Done (committed)

- `combat/tactics/gauntlet.py` GauntletTactics (L2 v0 above LOCAL's ForumTactics; Forum.yaml `forum.l2`): PUNISH (the
  far-target rule: an engagement spot free from the hero's arrival, t_run = 0.05 + |dx| / 17.5, through a swing +
  margin, one batched `MultiForecast.occupied` query on pick ticks), RUSH (isolated: no other enemy within 8 u; all
  spread: the least ETA by pursuit speed), KITE (8 u from the fastest pursuer on its side away from the others; with
  Tinies under the nearest Maestro; LOCAL's EVADE stands against KITE), Clawmaiden first / Minister last (`first` /
  `last`), under the flyers (Bellbearer, Reed, Minister, Maestro), the Clapper controller (face 3 u; slam: out 13 u or
  behind 3.5 u; jumps: behind the landing from `jump_landing`; Buddy Is Attacking; CC_CAST opens the GLIDE_SPIKE vocab
  hook, read by nobody until R7's glide_spike). Picks at 10 Hz + events, hysteresis 1.25, scores only.
- `clapper_facing` (forum_local): the Clapper's facing from flipX (flipX 1 = right; 15 R0 fights). The oracle backend's
  Entity.facing has the other convention for a standing Clapper, so R4's pocket rule (2) used a reversed facing (never
  reached in A0 / A0b). EVADE's weight factors named (EVADE_HIT_X / EVADE_RISK_X, bit-identical).
- ForumPlannerPolicy: GauntletTactics when `forum.l2.enabled` and `SSBOT_FORUM_L2` is not 0 / off (`fail:<p>` injects
  failures); per-episode `stats()["l2"]`; decision records get goal / goal_why / goal_t_end / l2_cands (the arbitration
  log: per candidate iid, type, window, need, isolated, ETA, priority, covered now).
- Tools: `forum_policy_replay --skip / --deadline-ms / --ticks-out`; `forum_a0_report` L2 section, hits / kills per
  episode.
- Tests: `tests/test_forum_l2.py` 13 (far target long / short window, rules, Clapper controller, two Clappers, facing,
  §4.4 item 4 three ways, switch, PUNISH hit count); `test_forum_tactics.py` 5 still pass. Full suite (tests +
  ssbot/tests, at 4c7a7a3, below-normal priority): 1142 passed, 2 skipped, 1 xfailed (the Bell Beast equivalence tests
  among them; no shared planner / forecast code was touched).

### Measured (forum.md 17.1-17.3; scratch outputs in this session's scratchpad `r6\replay\`)

- §4.4 item 4: forum_policy_replay 074719 i3 ep0 wave 0, 600 ticks, deadline inf: `SSBOT_FORUM_L2=fail:1` vs `=0`
  0 differing fields (plan, S, FORCED_RISK, mask, J) in 600 ticks.
- Open-loop replays (same fight, waves 0 / 3 / 6 / 7 / 13, 1000-2000 ticks each, loaded machine): L2 per tick p50
  0.014-0.047 ms, p99 1.4-3.3 ms; errors 0; unpredicted 0. Goals: wave 0 KITE(EVADE) 63 % / RUSH 31 %, wave 3
  Clawmaiden 91 %, wave 6 KITE under the Maestro 89 %, wave 7 RUSH 94 %, wave 13 RUSH 48 % / KITE(EVADE) 46 %.
- PUNISH does not hold in multi-enemy waves: of 2,331 candidates (waves 0 / 3 / 6) the engagement spot is covered now
  in 99.7 %, free after the arrival p50 0.017 s, p90 0.030, max 0.168 s, >= 0.35 s (one swing) 0 times; the same with
  the spot at 3.0 u instead of 1.8 u (not adopted); 1 PUNISH in wave 7. The idle enemies' support covers their
  surroundings all the time (A0's FORCED_RISK cause).
- The Clapper controller's branches all fire on the recording (open loop, ticks): wave 7 face 1,099, jump (behind
  the landing) 513, slam out 110 / behind (no room) 82 / stay behind 71; wave 13 face 790, slam 84 / 83 / 4,
  KITE(EVADE) 917 (the two within 8 u: nobody isolated).
- Pursuit speeds from 20 R0 caches (forum.md 17.1).

### Round 2 (2026-10-08 03:10-05:45, week push round 2; forum.md 17.5-17.6, plan R6 row note of 2026-10-08)

Merged main (already up to date at bc46dc9). Commits 6972e01 .. this one.

- **Round-1 A/B result** (forum.md 17.5; runs 015904 / 021942 L2 on, 020919 / 022951 L2 off, seeds 310000 / 310025,
  frozen ef036d5): 50 + 50 paired, all QUIT in wave 0. Paired (on - off): hits +0.16 (se 0.14), time alive -0.71 s
  (se 0.43), nail hits on enemies -0.52; DPS 3.24 vs 3.42; unpredicted 0 / 0; presses / s 7.28 vs A0b 7.75, plan-change
  rate 0.555 vs 0.615 (both not above A0b); L2 goal changes 33 / min (lens <= 10: failed). L2 did engage in wave 0:
  RUSH 55 % of the decision ticks (isolated 9,310, spread 4,449), KITE(EVADE) 43 %, PUNISH 0; targets Envoy 42 %, Reed
  31 %, Choristor 25 %; RUSH brought the hero to the target (|dx| p50 2.5 u vs 3.7 off) but not more attack plans (13 vs
  12 %). Hits: 122 under RUSH (69 from the rushed target, 53 from others), 91 under KITE(EVADE); the hit rate per
  decision tick is the same under RUSH, KITE(EVADE) and L2 off (0.0089 / 0.0085 / 0.0085). Tied to diag's early finding
  (HANDOFF 'Task wave-0 forensics'): the support saturates, FORCED_RISK's ranking ties and the pick falls to J, so the
  scores L2 sets do pick the plan, but every plan looks equally dangerous to the planner; the wave-0 bottleneck is the
  FORCED_RISK ranking, not whom to fight.
- **Target holding** (`gauntlet.py` `_pick` / `_choose`, Forum.yaml `forum.l2`): the rule (PUNISH / RUSH / KITE) is held
  `goal_dwell_s` 1 s (not into PUNISH); under it the kept target while eligible (RUSH: isolated, the kept one down to 8
  - `iso_hyst_u` 2 u; KITE: any) unless another scores `switch_x` 1.5 times more after `dwell_s` 4 s on it; a rushed
  target that gets company is kited with (KITE on it) until dwell_s; immediate switches only for a target gone, a PUNISH
  opening, a `first` type, the idle Clapper's turn; a move change of the target re-picks once instead of dropping it.
  Stats `tgt_switches`, `switch_kinds`; `forum_a0_report` gains `tgt_switches_per_min`, presses / s (latched presses /
  game time; the Forum policy's own presses_per_s is None) and the plan-change rate. Open-loop wave-0 replays (20
  episodes): target switches 23.8 -> 9.6 / min; live (round 2 full gauntlet, 25 episodes): **7.65 / min** (goal changes
  incl. rule changes on the same target 25.9 / min).
- **PUNISH bug fixed**: a spot whose run + swing did not fit the 2 s window query was never checked after the arrival
  and read window inf (always "go"); two such far targets flip-flopped as PUNISH every 0.1 s in a replay (negative
  scores defeat the 1.25 hysteresis). Now such a window is the query's end (too short).
- **Clapper controller, live** (forum.md 17.6.3; wave starts Forum_A_w7 / Forum_A_w13 rotated, eval, no real quits,
  seeds 310100-310131, L2 on vs off paired; v2 = frozen 171cf28): w7 time alive 19.7 vs 11.1 s (paired +8.6 s, se 1.5),
  hits / min 10.1 vs 16.6, nail hits on the Clapper 6.4 vs 2.1 per episode; w13 11.1 vs 9.2 s (+1.9, se 0.8), hits /
  min 19.0 vs 20.4, 10.9 vs 5.7 hits on Clappers; slam-collider hits 6 vs 21 (w7), 14 vs 19 (w13). No kills (230 HP,
  26 Reaper hits), all Q1 QUIT at about 3 hits. v2 changes from round 1: face 3 -> 4 u (its body reaches 2.25 u in
  front: approach overshoot into it), jumps: under and behind only when the run gets behind the landing 0.25 s before it
  lands and not through its body on the ground, else back off past the landing slam / rune circle (8.5 / 14.5 u).
  Remaining on-arm hits by branch: face <- rune bombs 44 (the cast: no safe ground cell, a jump in the near rune's 5-7
  frames; the planner's timing under the saturated support), jump <- body 14 on w7 (the way round flipped mid-jump,
  the hero turned back under the landing; the behind spot clamped at the wall), cornered slam (behind) <- body 7 on
  w13. v3 (716b539): the way round fixed at Jump Aim, behind only with room, a cornered slam goes out to the wall; and
  (a637d77) the idle Clapper's turn only when its spot is reached before the busy one's attack can end (w13 switched 13
  / min on turns). v3 (L2-on arm only, same seeds, run 050637): w7 body hits 14 -> 1 but slam / landing-slam hits 6 ->
  19 (stepping out / backing off while the target's hit weight, x 1.5 on jumps, pulled the J-greedy pick back in);
  v3 - v2 paired: w7 -0.33 s (se 2.3), w13 -0.92 s (se 0.7). **v4 (8754008)**: the target's hit weight 0 on the
  controller's stepping-away branches (CC_RETREAT), up slashes x 1.5 only on the way under. v4 (run 052126): **w7 time
  alive 30.6 s** (v4 - v2 +11.0 s, se 2.8; vs L2 off +19.5 s, se 1.9), hits 7.3 / min (off 16.6), slam hits 4 (off 21),
  body 0, 8.7 hits on the Clapper per episode; w13 unchanged (10.2 s, v4 - v2 -0.85 s, se 1.1; vs off +1.0). What is
  left on w7 is the cast: rune bombs 36, the jump cast's big rune 20 (it explodes about 3.3 s after the landing, when
  the controller is back at the face, inside its r 7.19 circle).
- **Full gauntlet re-run** (v2 171cf28, A0b protocol, seed 310200, 25 + 25 paired; runs 20261008_041945 on /
  043128 off): QUIT 25 / 25 both (Q1), hits 4.48 vs 4.48 per episode (paired 0.00, se 0.15), alive p50 14.2 vs 13.9 s
  (paired -0.45 s, se 0.66), FORCED_RISK 80.4 vs 80.1 %, unpredicted 0 / 0, presses / s 6.97 vs 6.89, plan-change rate
  0.582 vs 0.625, real quits 7 / 7 / 7, 0 wrong submits; L2 errors 0, L2 p99 1.3 ms; tick p50 11.3 / 10.3 ms, p99
  22.3 / 19.1 ms (machine load, below).
- **Machine load** (for the lead): from about 03:30 the machine ran at 100 % CPU (other tracks' forensics / replays /
  behaviour builds / three full test suites, mostly below normal). Live runs had 34-350 late ticks per episode (round 1:
  0-2) and "paused unasked" HARNESS_FAILs (the brain missed 14 frames, the oracle watchdog paused; one ends a whole
  combat_run): r6_ws.ps1's chunks failed after 7 and 1 episodes, diag's and r8's runs showed the same late ticks. From
  r6_ws2.ps1 on the instance-1 worker runs at AboveNormal (both arms alike) and a chunk cut by a HARNESS_FAIL is made up
  from its failed episode with the same seeds / rotation: 0 HARNESS_FAIL in 178 episodes (r6_ws2-ws4), late ticks 8-60
  per wave-start episode, 2.6-5.4 % of the full gauntlets' ticks. Round-2 absolute numbers come from worse timing than
  round 1's; the arms are paired.
- Checked (round-1 open issue): the reversed Entity.facing of standing Forum sprites matters nowhere else: the
  forecast places by flipX (enemy_tracker.FACES_LEFT); only R4's pocket rule (fixed) and L2 read an enemy's facing.
- Tests: `tests/test_forum_l2.py` 23 cases (round 1: 13; new: dwell, a move change keeps the target, opening / rule
  change, a rushed target with company, the idle Clapper's turn and its reachability, far PUNISH spots, the jump's back
  off / fixed way round, the cornered slam, no hit reward while stepping away); full suite (tests + ssbot/tests at
  8754008, below normal): 1152 passed, 2 skipped, 1 xfailed (716b539: 1151; Bell Beast equivalence among them; no shared
  planner / forecast code touched).

### Round 3 (2026-10-08 06:00-, the verifier's findings on ba7dddb; forum.md 17.5-17.6 "第 3 轮更正" notes and 17.7)

Commits 23e56af .. this one. Round 2's claims that did not hold are corrected in place (forum.md 17.5 / 17.6, the
plan R6 row note); below, the round-2 bullets above stand as written then.

- **Jump aim (high)**: Jump Aim (and Cast Jump) are instant states (one frame goes Jump Antic / Cast Slam Antic 2 ->
  Jump Aim -> Jump), so the tracker never ends a tick in Jump Aim and round 2's aim (keyed on that state) was never
  stored live: jump_how never fixed, the landing re-computed from the hero's x and the Clapper's in-air x (102 / 103
  in-jump branch flips in the v3 / v4 logs). First fix (23e56af): the take-off x kept from the antic ticks, the aim
  taken on the first tick past the antic, the way round fixed there (open loop on 052126: 7 / 8 jumps aimed, 0 flips
  after the aim). **Live it was worse**: 4a0c212's first block (20261008_064118, seeds 310300-307) w7 alive 15.7 /
  15.4 / 16.2 / 9.8 s vs v4 on the same seeds (064410) 45.0 / 34.3 / 10.9 / 17.1 s; the hero ran under the airborne
  Clapper on 8 / 8 w7 jumps and took its body 8 times (per-jump count over the decision logs, jump_live.py: v2 6
  crossings / 14 body, v3 0 / 0, v4 1 / 0). It turns to face the hero at Jump Aim, so "behind the landing" lies on its
  flight path: going there is going under it; v3 / v4's per-tick re-judgement with the drifting landing rarely went.
  The driver was stopped after that block (r6_ws.stop). **afb89a8** (aim kept, never under it: behind the landing
  only from its back side, else back off to the wall) was cornered live: w7 alive 16.0 vs v4 28.0 s (8 pairs, -12.0
  s, se 4.3), landing-slam hits 9 vs 4 (it jumps at the hero and lands 5 u short; "8.5 u in front of the landing" is
  the wall in a 28.8 u arena). **fd57819** (final): the jump stance is v4's live rule again, now stated as what it
  is: judged every tick from where the hero and it are now (jump_landing(its x, hero x, facing) is a stance rule,
  not a landing forecast), under and behind while the run fits 0.25 s before the landing and not through its body on
  the ground, else back off; up slashes x 1.5 back. No aim is stored any more (the jump cast's rune circle uses where
  it stands when the move ends). The round-2 claim "the way round fixed at Jump Aim" is withdrawn (it never ran);
  v4's per-tick rule crossed under it once in 25 jumps with 0 body hits. Tests: test_clapper_jump_judged_from_now,
  test_clapper_controller's jump part.
- **Buddy turn (medium, 23e56af)**: MultiForecast gave every Subject t_free 0.0, so the reach test of the idle
  Clapper's turn never held (a637d77 on: turn 0 times in v3 / v4's 32 w13 episodes; round 2's "13.2 -> 3.7 switches /
  min by the gate" was the rule switched off). Now t_free = the attack's start + its family's logged duration p0.5
  (enemy_tables.Family.dur from duration_s) - the origin; the walk's own earliest exit is ~0 (rare aborts). Only L2
  reads t_free (Bell Beast untouched). Tests: a synthetic Reed table in test_multi_forecast; production tables + a
  real MultiForecaster in test_forum_l2 (a slam 0.1 s in: the idle one's turn; 1.0 s in: none). Open loop on 052126:
  turn 6 times in 8 w13 episodes.
- **Goal switches (medium, the refuted "<= 10 / min passed")**: round 2 reported tgt_switches (7.65) against round 1's
  changes (33.0); the same lens live in round 2 was 25.9. The lens now: switches = tgt_switches + rule_changes (new
  stat: the same target under another rule, "RUSH>KITE" ...), the episode's first goal excluded (4.2 / min on its own
  in 13-15 s wave-0 episodes); both reported, forum_a0_report gains switch_kinds / rule_changes. Open loop wave 0 (26
  episodes of 041945 + 043128): round 2's holding 19.9 switches / min (7.7 target + 12.2 rule; RUSH>KITE 58,
  KITE>RUSH 18). Added rule_hyst_u (from KITE, RUSH needs one isolated by 8 + 2 u) and kite-with-the-kept-target only
  for a rushed one; a grid (forum.md 17.7.3) -> adopted goal_dwell_s 4, rule_hyst_u 2, dwell_s 8, switch_x 2.0 (Forum.yaml):
  8.2 switches / min open loop (3.9 target + 4.3 rule), changes incl. first goals 12.4.
- **Big rune (round-2 Next 1, 04dcad8)**: after a CC_JUMP_CAST the rune circle (6.62 u in front of the landing, r
  7.19) bursts about 0.75-0.87 s after the move ends (its tail, ChoirClapper.json); until rune_hold_s 1 s after the
  move the stance stays behind the landing (2.5 u, when the way round went under it and not through its body) or out
  past the circle (14.5 u, "rune: out", no hit reward), not at the face (v4 w7 took 20 hits there).
- **Wave-0 hits over all ticks (low)**: three paired full-gauntlet runs of rounds 1-2 (75 pairs): damage hits per tick
  0.00612 on vs 0.00565 off (+8 %, paired +0.11 / episode, se 0.11), alive -0.62 s (se 0.36); Choristor Body Damager
  28 vs 8 (paired +0.27, se 0.08): of the 28, RUSH on that Choristor 6, RUSH on another 8, KITE(EVADE) 14. Not fixed in
  L2 (the planner cannot rank the escape under the saturated support); re-check with diag's FR=seen.
- **Other corrections (low)**: v3's w7 body-hit drop came from "behind only with room", not the fixed way round;
  v2's w13 switches were turn 36 + better 3; the open-loop 23.8 / 9.6 came from different samples / settings (the
  final 4 s setting: 8.22, changes 23.0); presses / s on the Clapper waves 7.64 / 7.71 (L2 on) vs 6.48 (paired off),
  +18 %, plan-change rate 0.46 / 0.53 vs 0.50; v3 / v4 ran an hour after their control (not interleaved).
- **§4.4 item 4 re-run on the final code**: forum_policy_replay 074719 i3 ep0, 600 ticks, deadline inf,
  SSBOT_FORUM_L2=fail:1 vs =0: mode, target, plan, S, FORCED_RISK, mask, J equal in all 600 ticks (only the record's
  goal label differs: "LOCAL" vs none).
- **Live re-runs (r6_ws5.ps1, instance 1, interleaved blocks; forum.md 17.7.5)**, final code **fd57819**:
  wave starts w7 / w13 vs v4 (8754008), seeds 310300-310331, 16 pairs each (fd57819 runs 070851 / 071230 / 071658 /
  072800, v4 064410 / 065752 / 072118 / 072437): **w7 alive 37.4 vs 26.9 s (paired +10.6 s, se 4.0; 12 / 16
  longer)**, hits 6.9 vs 8.1 / min, big rune 2 vs 20, rune bombs 55 vs 30, landing / ground slam 11 vs 6, body 1 vs
  2, Clapper hits 9.9 vs 6.5 per episode; w13 -0.51 s (se 0.52; 5 / 16 longer), turn now fires (12), goal switches
  10.0 / min. Full gauntlet (A0b protocol, seeds 310400-310424, L2 on / off with the same checkout, 25 + 25
  interleaved; on 073208 / 074014 / 074246 / 075109 / 075408, off 073432 / 073649 + 073758 / 074531 / 074824 / 075636;
  one "paused unasked" HARNESS_FAIL in the off arm, made up with its seed): all QUIT in wave 0; paired hits -0.28
  (se 0.19), alive +0.78 s (se 0.71), Choristor body 5 vs 5; FORCED_RISK 82.2 / 80.0 %; unpredicted 0 / 0; real
  quits 3 / 3 / 3, 0 wrong submits; **goal switches 8.1 / min (pass; target 19 + rule 28; changes incl. first goals
  12.5)**, plan-change rate 0.575 (A0b 0.615, pass), **presses / s 7.88 vs A0b 7.75 (+1.7 %, a marginal fail; L2 off
  in the same blocks 7.31)**; L2 p99 1.07 ms; tick p50 / p99 10.5 / 19.8 ms (off 9.3 / 18.3). Machine at about 50 %
  CPU (round 2: 100 %).
- Tests: test_forum_l2.py 26 cases (+ the real-forecast turn test, the round-3 holding, the rune circle, the
  per-tick jump; the jump tests rewritten), test_multi_forecast.py + 1 (t_free); full suite (tests + ssbot/tests,
  below normal) at fd57819: 1156 passed, 2 skipped, 1 xfailed (4a0c212 / afb89a8: 1158 with the since-removed jump
  tests; Bell Beast equivalence among them). Shared code touched: MultiForecast's Subject.t_free (read by L2 only)
  and enemy_tables.Family.dur (new field).

### Running

- Nothing. Driver `C:\ssbot\sandbox\r6_ws5.ps1` (round 3) done (`r6_ws5.done`, log `r6_ws5.log`, one line per block
  in `r6_ws5_runs.txt`); `inst1.lock` released. Earlier drivers r6_ws2-ws4 done. Analysis scripts in this session's
  scratchpad `r6\r3\` (ws_anal3.py, jump_live.py, w0_hits.py, l2_sw3.py, jump_check.py).

### Next

1. Wave 0 is decided below L2 (the saturated support ties FORCED_RISK, diag): re-run the full-gauntlet pair and the w7 /
   w13 pair with diag's `SSBOT_FORUM_FR=seen` once it lands (rune bombs, the Choristor's body, the Envoy's charge).
2. w13 (two Clappers) did not improve with the working Buddy turn: a FOCUS goal for the final wave (pick one, keep the
   other behind it; clapper_face.md) and the KITE(EVADE) share when the two stand together.
3. The w7 rune bombs (55 of the hits left) are the planner's jump timing (the near rune's 5-7 frames).
4. Presses / s 1.7 % above A0b in the full gauntlet (more continuous RUSH after the holding): decide whether the lens
   should be per arm (L2 off in the same blocks: 7.31) or tune.
5. A Clapper kill needs about 26 Reaper hits (best w7 episode: 54 s, about 10 hits): tools / glide spike (R7).
6. Frozen checkouts to remove when done (no live run uses them): `C:\ssbot\live_r6_5d24020`, `live_r6_ef036d5`,
   `live_r6_f7a403c`, `live_r6_6d2f457`, `live_r6_171cf28`, `live_r6_716b539`, `live_r6_4a0c212`, `live_r6_afb89a8`
   (both withdrawn mid-run), then `live_r6_8754008` and `live_r6_fd57819` after the integration.
7. Main's `knowledge/1.0.30000/enemies/forum/` has no `*_hitboxes.npz` (git-ignored): the frozen checkouts take them
   from this worktree (`C:\ssbot\sandbox\r6_freeze.ps1`).

### Needs deploy

- Nothing (no oracle change).

## Forum integration 2026-10-08 (branch forum-integration-1008, worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_34e9717f-fa3-1`)

Main (41c4bd4, later d5b652a: docs only) plus the Forum tracks, one `git merge --no-ff` each, in this order: reactive
support `worktree-wf_08175c18-693-1` 8b1dd82 (it already holds the wave-0 forensics track `worktree-wf_fa16f06f-127-8`
2c4b089 and R8 up to bda1682), R8 clash `worktree-wf_814dfeea-b10-4` 7738698, harness recovery
`worktree-wf_814dfeea-b10-6` 01765f0, R5 model `worktree-wf_814dfeea-b10-1` 76e40ad, R5 value
`worktree-wf_814dfeea-b10-2` 9f28b0e, R6 v0 `worktree-wf_814dfeea-b10-3` 367862c, main d5b652a. Every listed head is an
ancestor of this branch. The track sections above keep their own text (their forum.md section numbers are the old
ones, see "forum.md numbering").

### Conflicts and how they were resolved

- `combat/forum_planner.py` (diag / reactive / R8 x R5 value; R5 value had ported diag's `seen` and stacked
  commit_rank on it): one `ForumConfig` with every track's fields (p_all, forced_rank incl. seen_cf, commit_rank,
  terminal + weights, react / esc_*, clash_*); `committed_fine_share` (seen_cf) kept; FORCED_RISK's keys stack:
  preselection (p_k 16) by seen count > seen first contact > the committed fine share (seen_cf) > P_cm > P_f > the latest
  first contact > J, then the rows with a clash branch appended (R8: ranked whatever their first contact; p_all keeps
  P for every row, the choice still in the preselection + clash rows); the final order hz > hz_soft > U > S > clash_p >
  keep > mkeep > V > seen > cf > P (clash-mixed) > P_cm > P_f > t_c > t_hit > J. A switch that is off leaves its keys 0
  on every row, so each track's own configuration orders exactly as on its branch (the escape check's FORCED_RISK tie
  set "keys above the share" is unchanged: P_cm / P_f are below it). `last_sel` (R5 value's audit hook) also carries
  sk_c and clash_p and is set before the escape pick ("first") with "chosen" after it; `last_info` has every track's
  fields (Pcm / Pf, seen, seen_cf, esc, dbg, tv).
- `train/forum_planner_policy.py`: one `_fcfg(clash)` (SSBOT_FORUM_FR incl. seen_cf, SSBOT_FORUM_REACT, the clash
  mode; PC / TV / T from ForumConfig's module defaults), the planner built with the crest, the clash mode and
  `PlannerConfig(T=fcfg.T)`; `__init__(..., crest, clash, branch_model)`; tactics = R6's `GauntletTactics` over LOCAL
  (SSBOT_FORUM_L2) with R5 model's forecaster (`branch=` when branch_model); `SSBOT_FORUM_AB` arms now also take
  `fr=seen_cf` and `rx=<SSBOT_FORUM_REACT value>` (the clash mode is not an arm key: it changes the candidate sets the
  planner is built with); the per-episode `replace(self._fcfg(self.clash), **arm)` keeps the clash mode; the decision
  log keeps every track's fields (tv, seen, seen_cf, esc, the L2 goal / why / t_end / l2_cands, clash); `stats()` has
  ab_arm, fcfg {forced_rank, react, commit_rank, terminal, T}, branch_model.
- `combat/multi_forecast.py` (R5 model x R6): `Subject` has both R6's t_free (start + family duration p0.5) and R5
  model's next_p.
- `tools/forum_policy_replay.py` (R5 value x R6): --skip / --ticks-out / L2 fields and the terminal-value stats.
- Docs: forum.md, HANDOFF, the plan rows: every track appended; the sections were put in number order (below).
- `tests/test_forum_planner.py`: diag's and R5 value's copies of `_with_collider` and the three seen tests were both
  merged (the later copies shadowed the earlier ones): R5 value's stacked versions (they loop commit_rank on / off)
  kept.

### forum.md numbering (three tracks had used section 17)

R8 clash 17 (17.9 placed at its end), R5 model 18, wave-0 forensics 19, **R5 value 20 (was 17)**, **R6 v0 21 (was
17)**, **reactive support 22** (the code had referred to a §20 that was never written; written at integration from
the track's code and its pooled A/B files, `C:\ssbot\data\m2_forum_react2\ab_pooled_vs_*.json`). Cross references in
the moved sections, the code comments / docstrings / tests / Forum.yaml and the plan's R5 / R6 rows follow (numbers in
tables that only looked like references, e.g. "17.6 %", were left alone, checked line by line); the track sections
of this HANDOFF keep the old numbers. Plan sec. 5 has a dated integration note (switches, defaults, the key order,
the numbering).

### Switches (defaults as the tracks left them)

| switch | values | default | what it does | track / facts |
|---|---|---|---|---|
| `SSBOT_FORUM_FR` | share, seen, seen_cf | share | FORCED_RISK's first keys: seen = frames each row's nominal box meets the damage colliders seen now, moved along their velocity; seen_cf = seen, then the share of stage-1 frames in the committed fine placements (attacks under way with a known entry) | diag, forum.md 19 |
| `SSBOT_FORUM_REACT` | off, delay, escape; + `+c` / `+i` / `+p5` | off | reactive support: an attack not started yet strikes no earlier than its wind-up (strikes.json least commit -> first damage, less the view's latency); escape adds the planner's escape check (safe ticks: first of 4 rows with a way out of every attack that may start; FORCED_RISK: among the first 8 rows tied on the keys above the share); +c committed attacks' later states, +i idle roots left to the body tube, +p5 the bell / pin / rune exceptions at p5 | reactive, forum.md 22 |
| `combat_run --forum-clash` (`ForumPlannerPolicy(clash=)`, `forum_policy_replay --clash`) | off, on, yellow, cont | off | R8 EV_CLASH: on = the clash branch + the keep-swinging continuation rows, GREEN only (DESIGN 3.5.6); yellow = also YELLOW (experiment, the lead's call); cont = the continuation rows only; run tag `_clash` / `_clashY` / `_clashC` | R8, forum.md 17 |
| crest (`ForumPlannerPolicy(crest=)`, from the encounter: `Forum_W` / fo_W = Wanderer, else Reaper; `forum_policy_replay --crest`) | Reaper, Wanderer | by encounter | kinematics (`hero_<crest>_forum.json`), slash shapes, the Wanderer dash-combo veto and down slash | R8, forum.md 17 |
| `SSBOT_FORUM_PC` | 1, 0 | 1 (on) | commit_rank: after P, the shares of stage-1 frames in the committed support (P_cm) and in the current attacks' fine placements (P_f), from stage 1's own query (`MultiForecast.occupied_split`) | R5 value, forum.md 20 |
| `SSBOT_FORUM_TV` | 0, 1 | 0 (off) | the terminal value (combat.terminal: E / trapped / overlap / H_exp into J, kill value into the target weights) | R5 value, forum.md 20 |
| `SSBOT_FORUM_T` | 36, 48 | 36 | the planner's horizon in frames (the policy's PlannerConfig follows it) | R5 value |
| `SSBOT_FORUM_HITBODY` | 1, 0 | 1 | hit targets from `Entity.hit_polys` (0: the R4 targets incl. the 5-47 u range triggers) | R5 value, forum.md 20.2 |
| `SSBOT_FORUM_AB` | `name:pc=0/1,fr=share/seen/seen_cf,rx=<react>;...` (one value each) | empty | arms switched per episode (episode k runs arm k mod n; `policy.ab_arm` in the attempts) | R5 value (+ fr seen_cf, rx: integration) |
| `SSBOT_FORUM_L2` | (empty) / 1 / on, 0 / off, fail:<p> | Forum.yaml `forum.l2.enabled: true` (on) | R6 v0's L2 target layer (GauntletTactics: PUNISH / RUSH / KITE, the Clapper controller) above LOCAL; 0 = the A0 LOCAL tactics bit for bit; fail:<p> injected failures | R6, forum.md 21 |
| `ForumPlannerPolicy(branch_model=)` | False, True | False | R5 model's branch model: per-enemy history (`EnemyTracker.mem`) and `Subject.next_p` (scoring only; nothing consumes it yet; combat_run does not expose it) | R5 model, forum.md 18 |

Note for the A/B: the merged default is NOT any single track's default. The diag / reactive / R8 arms ran without
commit_rank and without L2 (their branches did not have them); reproducing them on this branch needs
`SSBOT_FORUM_PC=0 SSBOT_FORUM_L2=0`. R5 value's arms ran without L2, R6's without commit_rank.

### Checks (offline, below-normal priority, NUMBA_NUM_THREADS 4)

- Full suite at 32db232 (all merges, before the integration tests): 1257 passed, 2 skipped (the vision window
  forecast test, the hitbox-table timing test on a busy machine: the same two as the tracks'), 1 xfailed
  (`scratchpad/fullsuite_32db232.txt` of this session).
  Full suite at 6c160ac (the final code): 1264 passed, 2 skipped (the same two), 1 xfailed (ullsuite_6c160ac.txt).
- New `tests/test_forum_integration.py` (7): the chosen FORCED_RISK row is the least of the choice set on the stacked
  keys for share / seen / seen_cf x commit_rank off / on, a switched-off key is 0 everywhere; a tick with every switch
  on (Wanderer, seen_cf, commit_rank, clash, escape, terminal value); the policy's combined switches and the AB arms.
- Bell Beast bit-identical with the Forum switches off: per-tick decisions (plan name, mask, S, FORCED_RISK, J, P,
  safe / allowed counts, the chosen command's hash, mode, stance) on `20261003_144536_BellBeast_eval_planner_oracle`
  i4_000, 3,000 frames, frozen main `C:\ssbot\live_int_41c4bd4` vs frozen integration `C:\ssbot\live_int_6c160ac`:
  oracle view 3,001 / 3,001 ticks identical (84 FORCED_RISK), vision-equivalent view 3,001 / 3,001 identical (1,023
  FORCED_RISK). Script `bb_ticks.py` / `bb_ticks.cmd` in this session's scratchpad (planner_bench's Bell Beast loop
  with a per-tick dump). The 50-episode Bell Beast oracle batch of the plan's merge rule was not run (the Forum
  priority; it is a live run on a non-Forum encounter).
- Shared code the Bell Beast path touches changed only by new bits / fields: kin_jit's AB_DOWN_SLASH /
  EV_PARRY_RECOVER, `Entity.hit_polys`, hero_damage's KNOWN_NEUTRAL (+ Cogwork Flier, Wallcling: not in the Bell
  Beast loadout), the harness recovery (episode / combat_run: no decision path).

### Smoke: the merged code runs (25 Forum_W episodes, 2026-10-08 10:45-10:54)

Frozen `C:\ssbot\live_int_6c160ac` (6c160ac = this branch's code; the commits after it are docs), driver
`C:\ssbot\sandbox\int_smoke.ps1` (locks inst0 / inst1 "integration", released; warm replay first), instance 0 13 + instance
1 12 episodes in parallel, Forum_W (Wanderer), eval, planner, oracle, real quits 0.2 (the A0b protocol), seed 360000,
`SSBOT_FORUM_FR=seen_cf SSBOT_FORUM_REACT=escape --forum-clash on`, everything else the merged defaults (commit_rank
on, L2 on, terminal value off, T 36). Runs `C:\ssbot\data\runs\m2\20261008_104557_Forum_W_eval_planner_oracle_clash`
(i0) and `20261008_104618_..._clash` (i1); report `C:\ssbot\data\runs\m2\int_smoke_report_6c160ac.json`
(forum_a0_report), summary script `smoke_summary.py` in this session's scratchpad.

- Every row: code_rev 6c160ac, one config_fp (228e3a98d296), fcfg {seen_cf, escape, commit_rank on, terminal off, T 36},
  clash on, crest Wanderer, L2 on. No crash, no HARNESS_FAIL, every worker exit 0.
- 25 / 25 QUIT in wave 0 (Q1 23, QS stalemate 2: "the killing-blow rule held back 20.0 s with no hit dealt": the
  Wanderer x3 crit bound, R8's open issue 2), 0 WOULD_DIE, 0 kills, 0 hits outside the support (0 unknown).
- In-game time per episode (attempt `ingame_s`) median 23.3 s, mean 25.6 s; 4.2 hits per episode, 9.8 hits / min
  (Envoy 39, Choristor 35, Reed 31; top colliders Envoy slash 16, Reed pin 10, Reed body 9, Choristor spin 9).
- FORCED_RISK 0.917 of the ticks (10.7 streaks / min); envelope audit clean (3,062 chosen safe plans all enveloped,
  core rows never left out). Escape: 2,855 safe ticks checked (486 passed), 31,964 FORCED_RISK ticks ranked (10,056
  passed, 6,766 moved off the order's first), 888 cut by esc_deadline_ms. Clash: the branch was skipped by its tier
  gate (GREEN only, DESIGN 3.5.6) on 33,633 of 33,684 FORCED_RISK ticks; 7 partial rows, 1 chosen: in wave 0 "clash on"
  is in practice the continuation rows.
- Compute: tick p50 median 10.2 ms, plan p50 / p99 medians 6.2 / 11.1 ms, late ticks 1.5 %.
- For orientation only (not paired, other seeds, other code): the reactive track's seen_cf + escape + clash on arm had
  a median 23.4 s and 10.3 hits / min, seen_cf + escape (clash off) 23.9 s / 10.1 (forum.md 22.2; the definition of
  its time column is the track's `ab.py`, not checked against ingame_s). The A/B is the next step's.

### Running

- Nothing. The smoke driver ended at 10:54 and released inst0.lock / inst1.lock; instance 4 (routes' Lace 2 collection)
  untouched.

### Needs deploy

- Nothing (no oracle change in any track).

### Next / open issues

1. The A/B (the next step): seen_cf + escape with clash off is the best measured arm so far (reactive pooled data,
   forum.md 22.2: 23.9 s vs seen_cf alone 22.9 s, paired +2.0 s, CI -0.5..4.7); clash on was worse on top of seen_cf
   (-3.2 s paired, significant) and seen_cf + escape + clash on -1.2 s (n.s.). The smoke ran the task's "seen_cf +
   clash on + escape" with the merged defaults (commit_rank on, L2 on): an A/B should include clash off and the
   commit_rank / L2 settings explicitly (`SSBOT_FORUM_AB` can switch fr / pc / rx per episode; clash and L2 need
   separate runs).
2. seen_cf with commit_rank on pays a second fine query for the committed fine share (`committed_fine_share`); R5
   value's note: take it from `occupied_split` (its committed fine part before the windows are or'ed in) to save it.
3. Clash rows in FORCED_RISK: P is mixed by the branch weight w, P_cm / P_f stay the plain row's (they only act on P
   ties); R8's note that the seen key counts the collider a swing would clash as a contact (clash rows ranked last
   under seen) is still open.
4. FORCED_RISK stays at 0.78-0.89 of the ticks with reactive support on (forum.md 22.2): what keeps wave 0's support
   saturated (support margins up to the 3.0 u search cap, body tubes, window placements of committed attacks, death
   tails, the export lag) is not decomposed yet (the reactive track's `forum_react_audit` groups2 run was cut off).
5. The Wanderer's x3 crit bound in the killing-blow rule (R8 open issue 2) ended 2 of the 25 smoke episodes as QS
   stalemates (20 s with the nail held back and no heal): it caps how long a Wanderer run can hold out even when it
   dodges well; the lead's call (DESIGN 3.5.6 / the kill rule), not changed here.
6. Frozen checkouts made here: `C:\ssbot\live_int_41c4bd4` (main, for the Bell Beast identity) can go;
   `C:\ssbot\live_int_6c160ac` is the smoke's. The tracks' own frozen checkouts are listed in their sections.

## Task wave-0 de-saturation (branch worktree-wf_34e9717f-fa3-2, 2026-10-08; forum.md §23)

Main 70f8324 + `forum-integration-1008` (6dce435) merged first. Facts: forum.md §23 (Chinese); plan sec. 5 dated note.

### Done (committed)

- `tools/forum_layer_audit` (b75b63a): the support split into layers (bodies, committed fine / window / family-wide /
  bbox / tail / chain, not-started, hazards, death, arena) over the planner's candidate rows on recorded ticks;
  leave-one-out at level 1 (not-started gone), margins x0 / x0.5, idle growth x0 / x0.5, the +-1 bin lag, a greedy
  peel, hindsight precision. Output `C:\ssbot\data\m2_forum_w0d\layers\` (30 Wanderer episodes, seen_cf + escape).
- Kill-freeze fix (default; `SSBOT_FORUM_KF=any` = before): `kill_freeze_s` counts only the kill's own freezes
  (`KILL_FREEZE_KINDS`, the Clapper's); it had given every wave-0 type a 0.4 s "kill freeze" from the hero's
  NailClashEffect / StartRecoil, so YELLOW's kill rule withheld every slash that might finish an enemy (the 0 kills).
- Switches (off by default):
  - `SSBOT_FORUM_REACT` extensions: `+n` (attacks not started out of the support; the escape check over every lock-in;
    pins / bells not thrown yet only their reaction-window reach; in the oracle view a throw family's templates (Reed
    RE_THROW, Bellbearer CB_THROW: every pin / bell ever thrown) replaced by its body tube and its hazards' paths, its
    tails and escape threats dropped), `+g` (the idle tube's growth held after the 5-frame reaction window), `+l`
    (light cone: the escape check asks the plan's end for a way out of the committed must-escape fine placements past
    the horizon, simulated over the 7 escapes), `+a` (aimed pins: a pin not thrown yet checked per row, aimed at where
    the row is 20 frames before each possible release).
  - `combat_run --forum-clash main` (`CLASH_MODES["main"]`): the clash pass also in a YELLOW at h >= 3 (never h 2, RED,
    pause pending), clean clash rows safe on the clash geometry with the hit-anyway bound <= 0.3, ranked after the plain
    safe rows; FORCED_RISK's seen keys skip a clash row's parry i-frames (R8's open note); clash depth 3.
  - `SSBOT_FORUM_MARGIN=state`: per-state support margins (`tools/forum_state_margins` -> knowledge
    `support_margins_state.json`: the largest held-out residual of the R0 contacts per Control state, >= 100 contacts
    else the family's; family-wide / tail / world / self templates keep the family margin).
- On by default (no switch until the fixer round's `SSBOT_FORUM_BELLS=off`; every arm of rounds 1-4 ran them):
  hit-back bells (a bell after Tink / Nail Hit is no hazard to the hero; the planner's own redirect leaves
  it harmless from the hit on); bells as hit targets of weight 0 (`ForumConfig.bell_hits`): a row whose swing meets an
  incoming bell before its contact gets the hit branch with the bell knocked back (also from a stage-1 contact).
- `multi_recall --react / --state-margins`; `tests/test_three_layer.py` (13 tests); one assert in test_forum_planner.

### Measured (forum.md 23.2-23.11)

- Decomposition: wave 0's saturation is redundant over layers; with the not-started layer gone only 3.5 % of
  FORCED_RISK ticks have a clear row; committed windows / family-wide union / tails / fine placements each cover every
  row on 50-64 % of them; margins are not the main cause (all 0: 6.2 %), idle growth is the body layer's (0: body +
  hazards alone 58.8 %); rows freed by dropping margins / growth are 93-96 % clear in hindsight, by dropping the
  committed layer only 77-87 %. Causes: family margins set by one state's few contacts (EN_CHARGE 2.96 u all from
  `Charge`, RE_DEFEND 2.62 u from `Multihit Clashed`), the `Charge` template holds the `Reset -> Charge` re-charges (38 u
  wide at entry), RE_THROW templates hold every pin ever thrown, pins in hand by their self template.
- Offline replay (10 episodes): the switches add 1-2 points of safe ticks (the committed layer is untouched).
- R2 held-out recall on `escape+n+g` + per-state margins: 375,940 / 375,940 at L2 / L3 / L4 (own type too), 1,802 /
  1,802 chain hooks (`C:\ssbot\data\m2_forum_w0d\recall_fresh_ngS_fca0416.json`): no held-out contact uncovered.
- Live, 4 rounds of 80 + 80 (paired same instance / seed; summaries `C:\ssbot\data\m2_forum_w0d\ab_round1..4.json`):
  - r1: int (integration best: seen_cf + clash on + escape) 0 kills, 0 / 80 wave-0 clears; intk (+ kill fix) 0.80
    kills, 11 / 80, +5.6 s; new (+ escape+n+g+l, clash main) 1.42 kills, 15 / 79, +21.4 s over intk (CI 10.1-33.6).
  - r2: newS (+ throw substitution, per-state margins, bells as targets) vs intk: +18.2 s (6.5-31.1), kills equal,
    clears 15 vs 16, hits / min 5.9 vs 7.3, damage per minute down ~25 %.
  - r3: noL (newS without `+l`) vs newS: clears 17 vs 11, kills 1.30 vs 0.86, +5.2 s (n.s.): no light-cone gain.
  - r4: newSa (`+a`) vs newS: clears 17 vs 23, -1.7 s (n.s.): no aimed-pin gain.
  - Support-outside hits 0 in all 640 episodes; 2 "unjudged" (no forecast kept at the lag: 20 % late ticks) both
    covered at every lag on replay (`scratchpad` `unk.py`).
- Recommended live configuration: `SSBOT_FORUM_FR=seen_cf SSBOT_FORUM_REACT=escape+n+g SSBOT_FORUM_MARGIN=state
  --forum-clash main` (r3's noL), kill fix default.
- Tests (33762ee): full suite 1249 passed, 2 skipped, 1 xfailed, plus 15 that failed only because that run had
  NUMBA_NUM_THREADS=2: their four files rerun with 4 threads, 73 / 73 passed.

### Fixer round (after the review, 2026-10-08 evening; code 5506b86; forum.md §23.12)

- Fixed (code, 5506b86):
  - `+n` covers a throw whose wind-up has started: the aimed-pin check is on with `+n` (`ForumConfig.pin_aim` = `+a`
    or `+n`); a Bellbearer throw keeps its templates until its release (`multi_forecast.REACT_KEEP_UNTIL_THROWN`:
    Throw Evade / Roof Avoid / Throw Antic). The support only gains coverage: the R2 recall (§23.8) cannot drop.
  - `+n` + escape: the escape check counts (`ForumConfig.esc_veto`): a chosen row that failed it, or that it could
    not check before its deadline with threats in reach, is S = 1 (YELLOW, never certified), and so is a CONTINUE of
    such a row; audit `esc_unsafe` / `esc_failed` / `esc_unchecked` / `esc_carried`, `last_info["esc"]["unsafe"]`.
  - The plan-lag hit metric: `hit_log` entries carry `lag` (the chosen plan 12 / 24 / 30 frames before: S, forced,
    clean clash, escape S = 1, aimed pin), `safe30`, `clash30`; stats `planned_safe`.
  - `ssbot.tools.forum_ab_summary <manifest...>` (in the repo; replaces the scratchpad `ab.py`): per arm and paired,
    with the decision-log plan-lag hits (any code version), the escape check's fail / cut rates and the pin hits with
    a throw under way.
  - `SSBOT_FORUM_BELLS=off`: the hit-back bells and bells as hit targets off together (default on, as before).
  - Docs: forum.md §23.2 (random-row baseline 63.8 % pooled; the freed rows' own precision), §23.4 (the light cone is
    an under-approximation, not the erosion; the bell rules had no switch), §23.7 (both arms ran the bell rules; the
    pin hits per minute are the same), §23.11 (the wave-0 clears came with the kill fix); §23.12 new; plan sec. 5 note.
  - Scratchpad: `bb_ticks.cmd` / `bb_ticks_ve.cmd` now call the reviewer's `bb_ticks.py` with its positional
    arguments (REC VIEW OUT FRAMES).
- Measured: rounds 1-4 re-summarised (`C:\ssbot\data\m2_forum_w0d\fix\sum_round1..4.json`): hits with an S = 0 plan
  in the 30 frames before them 0.10-0.23 / min on the new arms vs 0-0.06 on the controls; the escape check failed on
  37-42 % of the checked non-FORCED_RISK ticks. Live round 5 (80 + 80, `w0d_live2.ps1`, rec = 33762ee vs fix =
  5506b86, same env, seeds 365000, `sum_round5.json`): wave-0 clears 18 vs 19, time alive / kills / hits a minute
  equal (paired all n.s.: +0.8 s, +0.14 kills, -0.23 hits / min), support-outside 0 / 0, hits with an S = 0 plan in
  the 30 frames before 15 -> 9 (at 30 frames 14 -> 5), clean-clash rows followed by a hit within 30 frames 0.
- Tests (5506b86, NUMBA_NUM_THREADS 4, below normal): full suite 1268 passed, 2 skipped, 1 xfailed (6 new tests in
  tests/test_three_layer.py, one assert changed: `+n` now implies the aimed pins).
- Bell Beast: no module on its path imports a changed file (forecast.py mentions multi_forecast in a comment only):
  tick-identical by construction, not re-run.
- Not done: the clash-safety rule "the Wanderer's own clash rows (n_eff >= min_n)" (review low): the step that read
  the clash table code was refused by the permission classifier; the 0.3 bound and the YELLOW h >= 3 clash are the
  lead's call (behind `--forum-clash main`, off by default).

### Running

- Nothing. All drivers ended and released inst0-3 locks; instance 4 (routes) untouched.

### Needs deploy

- Nothing (no oracle change).

### Next / open issues

1. The committed layer (FORCED_RISK still 77 % of ticks; most pin hits fall there): rebuild the templates re-anchored
   per state (a re-entered `Charge` anchored at its entry, thrown hazards out of the thrower's templates) and
   re-certify (R2).
2. Offense: with the three-layer switches the bot lives longer but lands ~25 % fewer hits a minute (first kill 21-27 s
   vs the person's 17.5 s); in safe ticks only 2-4 % of chosen plans start with an attack (mostly CONTINUE): J /
   punish windows (R5 / R6). With the escape veto many safe-row ticks are S = 1 now (round 5: 62k ticks, half of them
   carried CONTINUEs): watch whether the YELLOW punish limit costs offense (round 5: kills equal).
3. After wave 0: wave 1's two Choristors (Spin Hit, whip), wave 3's bells and the spear blast are the main hits.
4. `+l` (light cone) and `+a` showed nothing in wave 0; the light cone is for the later waves' delayed area attacks.
5. Late ticks were 10-24 % with 4 instances; the escape check is cut 0.24-0.29 times a tick (unchecked rows are S = 1
   now): a faster check or a later deadline would turn some back into safe rows.
6. Lead decisions: the recommended configuration as the default (every switch still off); the clash main 0.3 bound
   and YELLOW h >= 3; the Wanderer-own-data rule for clash safety (not implemented, see above).
7. Frozen checkouts made here (can go after review): `C:\ssbot\live_w0d_b75b63a`, `45c4d6c`, `7a8afc9`, `016417b`,
   `d89f7ba`, `cc11343`, `fca0416`, `33762ee`, `5506b86`. The reviewer's scratchpad exports `wt/` and `int/` (each with
   a .venv) can go too.

## Base integration 2026-10-08 evening (branch worktree-wf_c8fb34ca-073-1, from main fa43977)

### Done (committed)

- Merged, in order: worktree-wf_34e9717f-fa3-2 (a6cb2a7: wave-0 de-saturation final after its fixer, contains
  forum-integration-1008), worktree-wf_14cec809-b56-1 (4ee4e3b: remaining hits, `tools/forum_remaining_hits`),
  worktree-wf_5bda75c4-6ae-1 (a39f281: the person's wins, `tools/forum_human_score`). forum.md: remaining hits stays
  section 24, the person's wins renumbered 24 -> 25 (headings, the internal 24.x references, the tool docstrings, the
  plan sec. 5 references). Planner code = a6cb2a7 (the two analysis branches only added tools).
- The verifiers' corrections (journals wf_14cec809-b56 / wf_5bda75c4-6ae), in place in forum.md 24 / 25 and the plan
  sec. 5 notes, with summaries in forum.md 24.8 and 25.11:
  - remaining hits: "the rounds 2-3 drop is round variance, not the changes" -> not resolved, the same-round DiD leans
    to round 2 cutting hits landed and kills (+2.18 eq. masks / min, p 0.04); avoidable = any clear row 4-36 frames
    before = 97.4 % (not 76 %), the 4-6 frame band 36.6 %, pins 100 % / 78 %; the trading claim is outcome-selected
    (5,010 hits landed = 1,252 masks vs 677 lost: net gain); clash-geometry class dropped (geometry <= 3 frames before
    contact); whip h <= 2 is 34 % at the attack start; Reed defence per the Reed paragraph (counter aims at the
    hero's height; wait out Defend or clash the counter; no down-slash trigger); retreat distances are observations;
    lock breakdown (dash ~30 %, attack ~27 %, Bind 21 masks 10 %, umbrella 8 %); eq. mask loss power in absolute
    terms (80 eps / arm: 1.5-2.0 masks / min); Poisson tests overdispersed.
  - the person's wins: the FORCED_RISK preselection keys AUC 0.755 / 0.779 (keep them, no learned score); fix 2's
    -24 % / -5 % is a whole-layer-removal upper bound; fix 1's cost is 3.5x the existing misses (Reed); keep is a
    replay artefact; the continuation bonus has little leverage (0.68 % of ticks); jump / dash timing <= 5.1 %; no +l
    in the replay; bot reference newS.
- `forum_human_score` (da8d104): the best row must have the person's attack / jump / dash press counts over frames
  1-18 (rising edges of the latched masks; the person's keys through the same hold filter), else the tick is outside
  the candidate set; the replay clears the planner's own `jump_until` / `macro_until` every frame; per tick the
  all-row hindsight base rates, the pick's distance from the person's path, one cause per tick (FORCED_RISK by the
  deciding key). Tests in tests/test_forum_human_score.py.
- `forum_remaining_hits` (abd6ba5): avoidable = any analysed tick 4-36 frames before with a clear row (+ the 4-6 band,
  + the 0.25 u margin variants); tests/test_forum_remaining_hits.py. Re-report `C:\ssbot\data\m2_forum_rh\report_avoid_v2.json`.
- `scripts/forum_human_rescore.cmd best|default <name>`: the plan's re-score check driver (run from a frozen checkout).

### Measured

- Re-score on the base code (frozen `C:\ssbot\hs_da8d104`, 32 segments, 0 errors; `C:\ssbot\data\m2_forum_hs\best_v2`,
  `default_v2`, `v2_summary.json`), best arm / default: FORCED_RISK 82.1 / 88.7 %; matched (presses equal and
  <= 0.35 u) 71.4 / 70.4 % (position only 81.0 %: the nearest row did not attack on 89 % of the person's attack
  ticks); matched rows unsafe 86.6 / 89.3 %, of them clear 88.8 / 89.1 %; misses 0.60 / 0.41 % of safe (32: Reed body
  31); matched rows clear 90.2 % vs all allowed candidates 80.9 % (pooled, open loop). Causes (best): outside 28.6 %,
  FORCED_RISK decided by J 22.8 / seen_cf 15.1 / seen 6.2 / P_cm 6.1 / first contact 4.3 %, safe but ranked behind 9.0 %
  (J 97 %: stance 55 %, CONTINUE 35 %), vetoed 4.1 %, the pick itself 0.7 % (pick within 0.35 u of the person 17.5 %).
  These are the baseline numbers of the plan's re-score check (plan sec. 5, forum.md 25.11).
- Full pytest (at 633e751; later commits are docs / a .cmd): 1290 passed, 2 skipped, 1 xfailed.

### Running

- Nothing (the two re-score runs finished; no game instance used, no lock taken).

### Needs deploy

- Nothing (no oracle change).

### Next / open issues

1. The same-round A/B the verifier asks for: frozen 016417b (new) vs fca0416 (newS), ABBA, then single switches.
2. Pins: 78 % had a clear row 4-6 frames before: find why the planner did not take it (planner / latency failure).
3. Bind: 21 masks were taken with the hero in BindCharge / BindBurst at the attack's start (a gap in the Bind commit
   condition).
4. The candidate set misses the person's timing (outside 28.6 %; 12.6 % of ticks the keys model is right but no row
   presses at that time): "wait k frames then jump / dash / attack" rows.
5. The per-group precision / layer-combination / AUC cuts of forum.md 25.4 / 25.8 were session scripts on the old
   matching; not recomputed.
6. `hit_log` attributes 43 % of whip chains to another Choristor (policy bookkeeping; not fixed).
7. Frozen checkout `C:\ssbot\hs_da8d104` can go after review.

## Task forum push 2 track A (branch worktree-wf_c8fb34ca-073-2, 2026-10-08 evening; forum.md §26)

Base: main fa43977 + `worktree-wf_c8fb34ca-073-1` (0cac216, the base integration) merged first (fast-forward). Track A
of the push: the person's decisions and tactics of 2026-10-08 in the planner / L2 / supervisor; track B's files
(multi_forecast, enemy_tables, candidates.py, the escape check) not touched.

### Done (committed)

- One switch, `SSBOT_FORUM_TA` (tokens joined by "+" or ","; `all`; empty = the planner before, bit for bit), also an
  `SSBOT_FORUM_AB` key `ta=<tokens>|none` (the supervisor's free mode and the L2 rules follow the episode's arm,
  `ForumPlannerPolicy._set_ta`); `stats.fcfg.ta` and the decision log's `ta` / `free` record it:
  - `free` (DESIGN 3.5.6 revision): `SupervisorConfig.free_until_hit` (forum_supervisor_config(free_until_hit=...)):
    h >= 2 and nothing pending -> no YELLOW restriction (kill primitives stay, no punish limit, parry / clash allowed,
    no killing-blow rule, so no QS), `SupervisorDecision.free` -> `FilterContext.free` (I3 passes the battle's last
    blow) and `ForumPlanner.clash_allowed` (any tier). The tier label is unchanged; Q1 (h <= 1, post-hit window), Q3
    (h = 2 with a mask-bypassing / long-chain / hazard / unknown support) unchanged.
  - `whip`: a clash-safe row whose clash meets CH_WHIP stays safe, J minus its hits and one hit weight
    (`ForumConfig.w_whip_clash`, audit `whip_clash_rows`); L2: in a Choristor's whip (antic + Whip 1-6) the stance
    leaves the whip's reach (5.3 u behind / 9.3 u in front: measured, the whip does reach 4.75 u behind), picks whose
    spot is in it get priority x 0.2, a whip starting / ending re-picks; PUNISH untouched.
  - `guard`: L2 hit weights by slash kind (`GoalPrefs.hit_kw`; the score kernel's target weights are [K, 4] now) for a
    Minister in Parry Stance / Parry Block (height bands low < 4.5 / mid < 5.2 / high <= 8.2 u over the floor, grouped
    within 8 u or alone; the table in forum.md 26.3) and a Reed in Defend / Block (never); the target's waiting stance.
  - `edge`: RUSH's stance 2.7 u outside the target body's edge (not its x).
  - `under`: J + 10 x (below.json: the hit rate 3 u in front less below) x the share of frames under a flyer.
  - `eml`: J - 4 x the hit weight x 1.154 masks x the stage-1 contact share; FORCED_RISK's order gets the key
    1.154 x P - hits landed / 4 after the first contacts (preselection and final order), the old keys untouched.
  - `kb`: the hit branch moves the hit enemy's own support and its reaction by its measured knockback from the hit
    frame (`forum_planner.knockback`, `_kb_shifts`; audit `kb_rows`); the first hit only.
- `tools/forum_knockback` (whip / Minister guard / knockback measurement over the Forum caches) ->
  `C:\ssbot\data\m2_forum_ta\measure.json`.
- `tools/forum_human_score.j_terms` calls the score kernel with its new signature (2ef0551; the first re-score crashed
  on every tick without it).
- Tests: `tests/test_forum_track_a.py` (18); `test_three_layer` one assert reshaped ([K] -> [K, 4] target weights).
- Docs: forum.md §26 (Chinese).

### Measured

- Whip (395 cached fights, `tools/forum_knockback`): Whip Hit 1-3 in front (to 8.75 u), 4 overhead, 5-6 sweep over its
  head to 4.75 u behind at the hero's height: the whip does reach behind; Whip Antic 0.817 s, Whip 1-6 0.05-0.067 s
  each, |vx| p50 0 (it stands still).
- Minister Parry Stance: transform 2.3 / 5.2 / 10.9 u over the floor (p5 / p50 / p95), stance collider 0.46-2.14 u
  below the transform, the counter (ParrySlash Hit 1-4) down to 2.8 u below; the guard push: Parry Stance -> Parry
  Block 1.34 u sideways / 0.25 u up at 12 frames (the person's question: it is barely pushed in the stance); Reed
  Defend -> Block 0.95 / 0.5 u.
- Knockback: side 0.45 u / frame for 8 frames (3.6 u), up 0.375 u / frame (3.0 u) for Reed / Minister / Bellbearer /
  Tiny / Clawmaiden; Maestro x0.65; Clapper side 0.72 u, up 0; no push in dashes / stabs / spins / counters (list in
  forum.md 26.4).
- Tests: full suite (code ~4f6842b) 1294 passed, 2 skipped, 1 xfailed; the track A / L2 / human-score files after the
  later changes 53 passed.
- Open-loop replays with `SSBOT_FORUM_TA=all`: no exception, L2 errors 0 (A0 600 frames; 20261003_074719 i3 ep0
  6,000 frames, waves 0-3).
- **Live smoke (10 episodes, instance 0, not an A/B)**: frozen `C:\ssbot\live_ta_4f6842b` (before the guard alone
  down-slash and the whip-not-in-PUNISH changes), recommended configuration (seen_cf + escape+n+g + state margins +
  clash main) + `SSBOT_FORUM_TA=all`, seeds 370000, run `20261008_185856_Forum_W_eval_planner_oracle_clashM`. Runs
  clean (no crash, 0 WOULD_DIE, 0 support-outside hits), all 10 Q1 in wave 0. **Much worse than round 5's fix arm**
  (same configuration without TA, 75 episodes, unpaired): median time 26.9 vs 34.8 s, hits / min 10.4 vs 4.8, kills
  0.40 vs 1.69 / episode, wave-0 FORCED_RISK share 0.82 vs 0.64, GREEN ticks 0.6 vs 15 %, KITE(EVADE) 63 vs 42 %,
  PUNISH 2 vs 11 %; goal hits 8.2 vs 6.6 / min.
- Per-token open loop (same recording, 15,654 frames, deadline 8 ms): chosen row differs on edge 20.3 %, free 3.8 %,
  eml 3.5 %, under 2.2 %, whip 0.8 %, kb 0.4 %, guard 0.3 %, all 23.0 % of the ticks; FORCED_RISK share unchanged by
  every token (0.265): the smoke's rise is behaviour (where the hero stands), and `edge` moves the most decisions
  (the RUSH stance 1.8 -> ~3.5 u from the Envoy: into the 3-5 u band of forum.md 24.4 where the bot meets the Envoy's
  slash 2.2x as often as the person). forum.md 26.7.
- Re-score (plan sec. 5; frozen `C:\ssbot\hs_ta_2ef0551`, `SSBOT_FORUM_TA=all`, best arm, 32 segments, 0 errors;
  `C:\ssbot\data\m2_forum_hs\ta_all_2ef0551[_summary.json]`) vs best_v2: FORCED_RISK 82.10 -> 82.09 %, matched
  71.4 -> 71.4 %, matched unsafe 86.57 -> 86.57 %, of them clear 88.82 -> 88.81 %, misses (of safe) 0.60 -> 0.60 %
  (flat); false alarms not down (kb acts in the hit branch only; the person's unsafe rows are stage-1 contacts,
  34,000 / 34,110); vetoed ticks 4.09 -> 2.87 % (wins 3.04 -> 1.04 %, the person's row not allowed 4.15 -> 1.43 %:
  `free`), wave 0 unchanged. The first re-score (`C:\ssbot\hs_ta_6b8f2ba`) errored on every tick (j_terms).

### Running

- Nothing (the smoke ended 19:06 and released inst0.lock; the re-score and the replays are done). Instance 4 (routes)
  untouched.

### Needs deploy

- Nothing (no oracle change).

### Next / open issues

1. The A/B (the merge step; same round, ABBA; `SSBOT_FORUM_AB` can rotate `ta=`): `ta=none` vs `ta=free` (the
   person's decision; check it does not raise hits), `ta=none` vs `ta=edge` (the smoke's prime suspect; if it fails,
   try the other reading of "the edge of the target's reach": outside the ENEMY's attack reach, about 5 u from an
   Envoy, not implemented), and `whip+guard+under+eml+kb` as one arm. Do not turn on `all`.
2. Knockback: the first hit only (the person's "two up slashes, then it is high enough" needs the second hit's
   branch); no down-slash push.
3. Minister mid band: L2 only zeroes the up slash in Parry Block and stands under it; the timed clash on its lunge is
   track B's candidate rows.
4. The harpoon in the guard bands (R7) is not in.
5. Untuned numbers: under 10 J per unit, eml 1.154 masks / contact and 4 hits / mask, edge 2.7 u, the band margins
   0.3 u, whip zone margins 0.3 u.
6. The main checkout has no `knowledge/1.0.30000/enemies/forum/*_hitboxes.npz` (git-ignored); the frozen checkouts here
   took them from `C:\ssbot\hs_da8d104`.
7. Frozen checkouts made here (can go after review): `C:\ssbot\hs_ta_6b8f2ba` (the re-score that crashed),
   `C:\ssbot\hs_ta_2ef0551` (the re-score), `C:\ssbot\live_ta_4f6842b` (the smoke).
