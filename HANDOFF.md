# HANDOFF - Task F (Forum, M2 W8) - round 2 (finished normally, 2026-10-03 ~01:10 PDT)

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_946a7803-63c-2`, branch `worktree-wf_946a7803-63c-2`.
Instance 2 (port 47019). Seeds 95100-97999 (used as --seed bases: 95100, 95200, 95300, 95400).

## Running job (left running on purpose: data collection)

- Run F: `C:\ssbot\data\runs\m2\20261002_231917_Forum_A_data`, instance 2, started 2026-10-02 23:19 by the chain
  `C:\ssbot\sandbox\fo_chain.ps1 -Tag F` (log `C:\ssbot\sandbox\fo_chain_F.log`) from the frozen worktree
  `C:\ssbot\live_fo_e589c0b`: `combat_run run --instances 2 --encounter Forum_A --mode data --policy data --hours 12
  --episodes 100000 --seed 95400 --threads 4 --timebox 1500 --rotate 5`. Ends by itself about 11:20 on 10-03 (12 h);
  about 4 episodes per hour; a recording closes every 5 episodes (i2_000 closed at 00:33, 5 episodes).
- Stop: `cd C:\ssbot\live_fo_e589c0b\brain; ..\scripts\uv.cmd run python -m ssbot.tools.combat_run stop
  C:\ssbot\data\runs\m2\20261002_231917_Forum_A_data` (ends after the current episode, <= 17 min). STOP_AGENTS also
  stops it. Live worktrees `C:\ssbot\live_fo_3fa0375`, `live_fo_7eb12de`, `live_fo_c86979f` are no longer used (can be
  removed with `git worktree remove`); `live_fo_e589c0b` runs run F.

## Runs (all fo_A, data policy, instance 2)

| run | code | episodes | note |
|---|---|---|---|
| 20261002_221727_Forum_A_data | 3fa0375 | 2 | false CLEAR before the finale (Tiny kills; fixed 7eb12de) - not used for tables |
| 20261002_223640_Forum_A_data | 7eb12de | 2 | complete gauntlets |
| 20261002_230325_Forum_A_data | c86979f | 1 | --timebox 1500 (the episode took 936 s) --rotate 5 |
| 20261002_231917_Forum_A_data | e589c0b | 7+ (running) | + pocket mode with only Clappers left |

## Done this round (commits 7eb12de .. 0da25b9)

- Fix: GauntletTap counted the Maestro's summon kills in the DecrementEnemy replay (false CLEAR).
- Multi-enemy behaviour tables: `ssbot/knowledge/gauntlet_tables.py` + scanner extensions in `behaviour_tables.py`;
  `behaviour_build --encounter Forum`. First tables from 8 complete gauntlets: `knowledge/1.0.30000/enemies/forum/
  <Enemy>.json` + `coverage.json` (npz templates not committed, 25 MB: rebuild with the command below).
- `ssbot/tools/forum_pocket.py` (pocket check), `combat_run --timebox`, data policy pocket mode, forum_counts from the
  specs (incl. Song Automaton Tiny). Tests: test_gauntlet_tables.py, test_forum_pocket.py, test_gauntlet.py.
- forum.md sections 8 (TERRAIN, dome, pocket = HeroBoxWallSlide x 14.04-14.92 y 12.53-13.97), 9 (journal names,
  export per type, multi-hit colliders, source paths, kill sources), 10 (Clapper jump and the pocket), 11 (tables).

## Key measurements

- Names (game journal): Choristor = Song Pilgrim 03, Envoy = Song Pilgrim 01, Choir Bellbearer = Pilgrim 03 Song.
- Kill sources: Cogfly = "Damager" (Generic 3), Garmond = WildSlash Enemy Damager / Stomp Damager / Stomp Splash
  Damager / Charge Damager (Generic 5); Garmond deals most of the Clappers' damage.
- Clapper jump: target hero x + 5 (facing left) / - 5, vy 38, gravity_scale 1.4 (g_eff 84), apex +8.6, body top
  15.86. With the hero in the pocket the Clapper only takes Far Range choices (Slam Range top y 10.82).
- Pocket closest approach (10 fights, 264 jumps): slam 2.04, rune slam 2.00, bombs 6.67, entry 4.15, body >= 4.73;
  jumps with the hero on the wall at takeoff >= 1.82 (median 4.3); only jumps from flush against the left wall (x
  15.36-15.95) enter the pocket (7 of 10 such takeoffs, 2 hits there).
- Tables: 18,084 contacts, 19 fail validation; all A attacks >= 200 within ~2 h more except the Envoy (one per gauntlet:
  jump slash 15 h, charge 13 h, ambush 46 h, hop slash never) and the entries.

## Next

1. Rebuild the tables with run F's later recordings: `cd brain; $env:NUMBA_NUM_THREADS=4; ..\scripts\uv.cmd run python
   -m ssbot.tools.behaviour_build C:\ssbot\data\runs\m2\20261002_223640_Forum_A_data
   C:\ssbot\data\runs\m2\20261002_230325_Forum_A_data C:\ssbot\data\runs\m2\20261002_231917_Forum_A_data --encounter
   Forum --allow-failed-validation` (below-normal priority; ~90 s per episode) and update forum.md §11; then
   `python -m ssbot.tools.forum_pocket <same runs>` for §10.
2. Envoy: a targeted collection (only the wave-0 Envoy, kept alive) or treat its rare attacks as once-per-fight.
3. Pocket mode climbs rarely (145 of 5621 wall frames at y >= 13.3): a reliable wall-climb routine (kinematics chain's
   wall-jump model) before measuring the Clappers' choices with the hero up there for long.
4. Remaining validation failures (19): see forum.md §11. Oracle `allies` export still undeployed; Ascendant's Grip
   pickup location unknown.
