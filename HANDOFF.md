# HANDOFF - Task F (Forum, M2 W8) - round 2

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_946a7803-63c-2`, branch `worktree-wf_946a7803-63c-2`.
Instance 2 (port 47019). Seeds 95100-97999 (used: 95100, 95200, 95300, 95400 as --seed bases).

## Running job (may keep running after the agent returns)

- Data collection, arm A, instance 2: chain `C:\ssbot\sandbox\fo_chain.ps1 -Tag F` (log `C:\ssbot\sandbox\fo_chain_F.log`)
  starts `combat_run run --instances 2 --encounter Forum_A --mode data --policy data --hours 12 --episodes 100000
  --seed 95400 --threads 4 --timebox 1500 --rotate 5` from the frozen worktree `C:\ssbot\live_fo_e589c0b` once run E
  (`20261002_230325_Forum_A_data`, stop requested after its episode 0) has ended. Run F's dir is printed in the chain log
  (`C:\ssbot\data\runs\m2\2026100?_??????_Forum_A_data`, the newest Forum_A_data dir).
- Stop: `cd C:\ssbot\live_fo_e589c0b\brain; ..\scripts\uv.cmd run python -m ssbot.tools.combat_run stop <run dir>`
  (ends after the current episode, about 10-15 min); before run F has started: create
  `C:\ssbot\sandbox\fo_chain_F.stop`. STOP_AGENTS also stops it.
- Recordings rotate every 5 episodes (closed every ~1-1.2 h), so `behaviour_build` (closed recordings only) can be run
  any time.

## Runs so far (all fo_A, data policy, instance 2)

| run | code | episodes | note |
|---|---|---|---|
| 20261002_221727_Forum_A_data | 3fa0375 | 2 | false CLEAR before the finale (Tiny kills, fixed 7eb12de) |
| 20261002_223640_Forum_A_data | 7eb12de | 2 | full gauntlets (848 s, 737 s of 900 s timebox) |
| 20261002_230325_Forum_A_data | c86979f | 1 | --timebox 1500 --rotate 5; stopped for the pocket policy |
| run F | e589c0b | ... | + pocket mode in the finale (data_policy POCKET_MODES) |

## Done this round (commits 7eb12de .. e589c0b)

- Fix: GauntletTap counted the Maestro's Song Automaton Tiny kills in the DecrementEnemy replay -> false CLEAR.
- `ssbot/knowledge/gauntlet_tables.py`: one BehaviourBuilder per Forum enemy type (FORUM_SPECS: families per type from the
  FSM dumps), fed per enemy entity; hazard aliases by circle radius ("damager"); contact attribution by GameObject name,
  collider child ("Colliders/Collider ParryStance"), nearest live subject, per frame for blocked stretches; scanner
  extensions in behaviour_tables (idle family, kill = death, late spawns, several armed hazards per type, multi-hit
  follow-ups). `behaviour_build --encounter Forum` writes `knowledge/1.0.30000/enemies/forum/<Enemy>.json/_hitboxes.npz`
  + `coverage.json` (counts, rate, hours to 200). Tests: tests/test_gauntlet_tables.py.
- `ssbot/tools/forum_pocket.py`: closest approach of every Clapper collider / hazard to the cling pocket.
- `combat_run --timebox`; data policy pocket mode with only Clappers alive.
- forum.md sections 8 (TERRAIN, the dome ceiling, pocket = HeroBoxWallSlide x 14.04-14.92 y 12.53-13.97), 9 (journal
  names: Choristor = Song Pilgrim 03, Envoy = Song Pilgrim 01, Choir Bellbearer = Pilgrim 03 Song; export per type;
  multi-hit colliders; source paths; kill sources: Cogfly = "Damager", Garmond = WildSlash/Stomp/Stomp Splash/Charge),
  10 (Clapper jump: aim hero x +- 5, vy 38, g_eff 84; only Far Range choices while the hero clings; closest approach per
  attack; only a jump from flush against the left wall reached the pocket, 2 of 62 jumps), 11 (first tables).

## Next

1. Rebuild the tables when more recordings close:
   `cd brain; ..\scripts\uv.cmd run python -m ssbot.tools.behaviour_build <runs...> --encounter Forum
   --allow-failed-validation` (NUMBA_NUM_THREADS=4, below-normal priority; ~45 s per episode scan) and update forum.md §11.
2. `forum_pocket` on the run F recordings (pocket mode): Clapper choices and jump aims with the hero up there; check the
   "flush takeoff" rule (forum.md §10.4).
3. Residual validation failures (small): Clawmaiden spear blast contacts after her death/attack (no owning instance),
   Bellbearer bells 2-4, Clapper Slam Collider 2 in Slam Recover (per-state set).
4. Oracle allies export still not deployed (helpers/Cogflies not in STATE); Ascendant's Grip pickup location unknown.
