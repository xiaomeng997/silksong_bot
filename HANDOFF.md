# HANDOFF: chain H (pause / quit harness and safety follow-ups, M2 W5)

Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_c0d56d51-4cb-4`, branch `worktree-wf_c0d56d51-4cb-4`.
Instance 4 (port 47021), seeds 100000-104999, savestate prefix pq_ (none made). Facts: docs/facts/1.0.30000/pause_quit.md.

## Done
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

## Running
- Pause stress campaign, detached (Win32_Process Create, survives this session): worktree
  `C:\ssbot\live_pq_e34da27` (e34da27, numba prewarmed), instance 4, seeds 100600-104999 (4400 trials, about
  37 h at 30.4 s per trial), run dir `C:\ssbot\data\runs\m2\20261003_010522_BellBeast_eval_planner_oracle_inject`,
  launcher log `C:\ssbot\sandbox\pq_campaign.log`, worker log `<run dir>\worker_i4.log`.
  Stop (graceful, after the current trial): from `C:\ssbot\live_pq_e34da27\brain`:
  `..\scripts\uv.cmd run python -m ssbot.tools.combat_run stop C:\ssbot\data\runs\m2\20261003_010522_BellBeast_eval_planner_oracle_inject`
  (or C:\ssbot\sandbox\STOP_AGENTS). Instance 4 holds SsOracle.dll while it runs: stop it before deploying.
  Summarise: `..\scripts\uv.cmd run python -m ssbot.tools.pause_stress <run dir> --quiet --json <run dir>\pause_stress.json`
  (reads every recording: run it at below-normal priority, about 1 s per trial).

## Needs deploy
- 10d3948 oracle ACTION EXCLUSIVE flag (HoldFilter.Exclusive, brain-lost Pause tap exclusive, HELLO action_flags,
  input.stats hold.released_early). Brain already sends the flag. After deploying, the Python key guard can model
  EXCLUSIVE (keys_clear would then always pass) to save its 0-2 frame wait, if the lead wants.

## Next
- To reach 10^4 trials: another seed range (this chain's ends at 104999) or more instances.
- G1 also asks for greyed-Quit, focus-loss and Steam-overlay injections (not done here).
- Decide whether the supervisor's h for the tier (not only Q1) should also use the worst known event when the
  support is certified empty (at 3 HP with the boss underground the tier is GREEN today).
- Lead: merge facts/pause_quit.md into probes.md as needed; the supervisor Q1 change (10bfb66) is a behaviour change.
