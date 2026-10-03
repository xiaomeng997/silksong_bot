# HANDOFF: task V (Bell Beast in the vision-equivalent view), fixer round

Worktree C:\modeling\silksong_bot\.claude\worktrees\wf_946a7803-63c-1, branch worktree-wf_946a7803-63c-1.
Findings: docs/facts/1.0.30000/m2_vision_view.md, "第三轮" (round 3 = this fixer round) at the end; it also marks
round 2's live numbers (sections 10-12) as measured with an oracle supervisor / pause machine.
Live runs go from the detached worktree C:\ssbot\live_vv (checked out at the commit under test, numba prewarmed
with planner_bench on a recording). Instances 0 and 1 (ports 47017 / 47018) are left running idle; the lead runs
launcher --restore.

## Done (fixer round, commits d9faaff .. 4a90331; later commits are docs)

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

## Measured (details in the facts file)

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

## Stopped here (STOP_AGENTS, 2026-10-03 07:33): not done yet

- Oracle-view regression on the final code (both views share the left-tink fix, the exact-path caches and the
  unpredicted accounting): about 60 episodes, e.g. from C:\ssbot\live_vv\brain (already at 4a90331, numba warm):
  `..\scripts\uv.cmd run python -m ssbot.tools.combat_run run --instances 0,1 --encounter BellBeast --mode eval
  --policy planner --view oracle --threads 4 --real-quit 0.2 --seed 92000 --episodes 32`.
- Offline property test on the final code (tools/bell_hit_audit, both views; last run at 8809999) and rec_stats
  (pogo hits per charge) on 20261003_053033.
- Nothing of this task is running.

## Next

- See the facts file, round 3 section 9 (remaining issues): off-screen bell columns and the union shortcut, the rage
  prune's hit-count assumption (M3), the persistent-bias size (M3), bursts / rage pattern / Dig In pogos.
- To stop a running job: `..\scripts\uv.cmd run python -m ssbot.tools.combat_run stop <run dir>` from
  C:\ssbot\live_vv\brain (or this worktree's brain).
