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

### Running

- 10^4 pause stress campaign, restarted on the final code: worktree `C:\ssbot\live_pq_3bc9da8` (the name is stale: it
  is checked out at 3afa1e1, numba prewarmed), instance 4, seeds 105330-109999 (4670 trials, about 39 h at ~30 s),
  run dir `C:\ssbot\data\runs\m2\20261003_122030_BellBeast_eval_planner_oracle_inject`, launcher log
  `C:\ssbot\sandbox\pq_campaign_q2.log`, started detached (Win32_Process Create) with
  `C:\ssbot\sandbox\pq_campaign_start.cmd C:\ssbot\live_pq_3bc9da8 105330 4670 C:\ssbot\sandbox\pq_campaign_q2.log`.
  Stop (graceful, after the current trial): from `C:\ssbot\live_pq_3bc9da8\brain`:
  `..\scripts\uv.cmd run python -m ssbot.tools.combat_run stop C:\ssbot\data\runs\m2\20261003_122030_BellBeast_eval_planner_oracle_inject`
  (or C:\ssbot\sandbox\STOP_AGENTS). It holds SsOracle.dll: stop it before the EXCLUSIVE deploy. Summarise with
  `pause_stress <run dir> --quiet --json <run dir>\pause_stress.json` (below-normal priority).
- Chain H's campaign 20261003_010522 was not running (it died at 07:13 after 722 trials, see Next 2); a 23-trial start
  on d0c2327 (20261003_120827, seeds 105300-105322) was stopped to pick up 3afa1e1.

### Needs deploy

- Nothing new from this chain. The EXCLUSIVE oracle flag already in main: checklist in pause_quit.md section 8 (stop
  this chain's campaign on instance 4 first; it holds SsOracle.dll).

### Next

1. A/B of `bind.reserve_at_full_hp` (keep 9 silk at full HP) now that Q1a binds whenever it may: Binds and CLEARs vs
   Silkspear damage and time to kill.
2. Chain H's campaign died at 07:13 (722 episodes, 20261003_010522): `load_slot` after a real quit timed out waiting
   for gameplay (TimeoutError in the worker); the worker has no retry there. Watch the restarted campaign for the same.
3. Safe spots for later encounters (Forum left wall top, Lace 2 arena): need a cling / double-jump primitive in the
   planner before `SafeSpot.kind == "wall"` can be used; verify each with coverage_map first.
4. Live workdirs: `C:\ssbot\live_pq_72baaf3` (first live check; can be removed with `git worktree remove`) and
   `C:\ssbot\live_pq_3bc9da8` (despite its name checked out at the final code commit, numba warm; runs the campaign).
