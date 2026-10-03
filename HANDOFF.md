# HANDOFF - Task F (Forum, M2 W8) - round 3, fixer (finished normally, 2026-10-03 ~02:20 PDT)

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_946a7803-63c-2`, branch `worktree-wf_946a7803-63c-2`.
Instance 2 (port 47019). Seeds 95100-97999 (used as --seed bases: 95100, 95200, 95300, 95400, 95500).

## Running job (left running on purpose: data collection with the fixed code)

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

## Runs (all fo_A, data policy, instance 2)

| run | code | episodes | note |
|---|---|---|---|
| 20261002_221727_Forum_A_data | 3fa0375 | 2 | false CLEAR before the finale - not used |
| 20261002_223640_Forum_A_data | 7eb12de | 2 | complete gauntlets |
| 20261002_230325_Forum_A_data | c86979f | 1 | complete |
| 20261002_231917_Forum_A_data | e589c0b | 10 | complete, pocket mode (85 % of the frames on the wall with only Clappers left) |
| 20261003_014254_Forum_A_data | 9a14574 | running | live check of the fixes: ep0 CLEAR, f_end = freeze + 270, waves in order (2 -> 3: 1.5 s) |

## Done this round (fixer; commits 379e33e .. e9eddb4)

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

## Key measurements

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

## Next

1. When run G has 2-3 more closed recordings: rebuild (`cd brain; $env:NUMBA_NUM_THREADS=4;` below-normal priority;
   `..\scripts\uv.cmd run python -m ssbot.tools.behaviour_build C:\ssbot\data\runs\m2\20261002_223640_Forum_A_data
   C:\ssbot\data\runs\m2\20261002_230325_Forum_A_data C:\ssbot\data\runs\m2\20261002_231917_Forum_A_data
   C:\ssbot\data\runs\m2\20261003_014254_Forum_A_data --encounter Forum --allow-failed-validation`, ~110 s per
   episode) and regenerate §11 (script logic: numbers from coverage.json only); watch the held-out shares fall.
2. Kill-frame contacts: the scanner ends an instance on the kill before the same-frame contact; give the dying body a
   short "death" window (and the finale Clapper's 'Start Battle?' after ZERO HP) so the planner sees it.
3. Envoy targeted collection; reliable wall climb for the pocket (145 of 5621 wall frames reached the top).
4. Oracle allies / room.battles exports still not deployed; Ascendant's Grip pickup location unknown.
