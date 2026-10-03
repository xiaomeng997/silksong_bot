# HANDOFF - Task F (Forum setup, M2 W8 first half) - stopped by STOP_AGENTS

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_946a7803-63c-2`, branch `worktree-wf_946a7803-63c-2`.
Stopped 2026-10-02 ~21:06 PDT: `C:\ssbot\sandbox\STOP_AGENTS` ("lead: 5-hour window at 86%... Resume after 22:40 PDT").
The stop file was written at 20:54:09, two minutes after GATE_DONE; I noticed it only at ~21:05, so the live steps on
instance 2 between 20:52 and 21:05 (savestates, checks, cling test) ran after it. No live run or job of mine is running
now (instance 2 is idle in Hang_04; the two idle-priority UnityPy scans finished).

## Done (all committed)

- Facts: `docs/facts/1.0.30000/forum.md` (Chinese): arena structure, the 14 BattleWaves (enemy types, spawn points, HP,
  damage), how the gauntlet ends (EndBattle, EnemyBattleEndSlow freeze, hang04Battle, lamp opens the gates), helper
  flags and the Call Ally FSM (Garmond 4 s after wave index 1), LoadedFromMenu clears the aid flags, tool / crest ids
  (Cogwork Flier, Wallcling, Reaper), Reaper chapel Greymoor_20b/20c, Cogfly craft table Hang_09 (8 s pause-disabled),
  bundle geometry, savestate composition + in-game checks (section 7). Sections 8 (TERRAIN) and 9 (export check) still
  need the live numbers below.
- Oracle (built with -p:Deploy=false, NOT deployed): 788aaa8 STATE `room.battles` (BattleScene wave / started /
  completed / enemies / to_next); cd215cc STATE `allies` (Cogflies + BattleScene "* Fighter" NPCs). -> needs deploy.
- Python: `ssbot/train/gauntlet.py` (GauntletTap, WaveSim, live_enemies / WAITING_STATES), FORUM encounter +
  `Forum_A/B/C/A5` variants and `forum_intro` in `encounters.py`, `make_tap` + `AttemptRecord.gauntlet` in `episode.py`,
  `GauntletDataPolicy` in `data_policy.py` (incl. CLING mode), `combat_run` uses them, `tools/forum_counts.py`
  (attack counts per enemy type, hours-to-200 estimate), `probes/forum_setup.py`, tests `brain/tests/test_gauntlet.py`.
- Savestates (C:\ssbot\sandbox\savestates): `fo_A`, `fo_A5`, `fo_B`, `fo_C` (game-written, verified: loadout, flags,
  no double jump / Silk Soar), plus intermediates `fo_pre_help7`, `fo_pre_nohelp7`, `fo_p7_s3`, `fo_*_raw`, `fo_*_fix`.
- Verified live: intro reaches the battle start (x ~33, wave 0 spawn ~4.7 s later); Garmond enters and kills in A and
  B, stays Dormant in C; wall cling with the Grip on the left wall (highest still cling y 13.60 at x 14.27).

## Next (in order)

1. Read `C:\ssbot\sandbox\forum_setup\terrain_A.bin` (TERRAIN of Hang_04 from the check; `ssbot.oracle.messages.Terrain`)
   and fill forum.md section 8 (floor, walls, ceiling steps, platforms).
2. Start the arm A data-collection run on instance 2 (detached, so it survives the agent):
   `cd brain; Start-Process -WindowStyle Hidden ..\scripts\uv.cmd -ArgumentList "run python -m ssbot.tools.combat_run run
   --instances 2 --encounter Forum_A --mode data --policy data --hours 12 --seed 95000" -RedirectStandardOutput
   C:\ssbot\sandbox\fo_data_A.log`. After 3-4 episodes run `python -m ssbot.tools.forum_counts <run dir>` for the hours
   estimate (Clapper attacks are the slow ones: 1 Clapper in wave 7, 2 in the finale). Add instance 4 only if the CPU
   allows. Stop: `python -m ssbot.tools.combat_run stop <run dir>`.
3. Add "Song Automaton Tiny" (the Maestro's summons) to `forum_counts.ATTACKS` once its attack states are seen in data;
   check which "Damager" / "Enemy Damager" kill sources are the Cogfly vs Garmond / Zaza.
4. forum.md section 9: export check from the first recordings (every wave enemy with colliders and damage bits,
   Clapper Bomb Cast projectiles, Handmaiden spear); helpers and Cogflies are missing from "ents" by design -> the
   `allies` export (needs deploy).
5. Ascendant's Grip pickup location is still unknown (no string reference in the scene bundles).
