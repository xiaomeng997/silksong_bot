# HANDOFF: task V (Bell Beast in the vision-equivalent view)

Worktree C:\modeling\silksong_bot\.claude\worktrees\wf_946a7803-63c-1, branch worktree-wf_946a7803-63c-1.
Findings: docs/facts/1.0.30000/m2_vision_view.md (round 2: sections 1-11 at the end).
Live runs go from a separate detached worktree C:\ssbot\live_vv (git worktree of this branch, checked out at the
commit under test, numba prewarmed with planner_bench). Instances 0 and 1 (ports 47017 / 47018) were restarted by
this task at about 22:25 PDT (they had exited); the lead runs launcher --restore.

## Done (round 2, commits bb568e5 .. ec62558)

- bb568e5 no logged velocities (vision/track.VelocityTracks), cues as noisy detections; 71f2478 attack bells on
  exact paths (bell_track.AtkBellTracks) and the burst's attack-bell unions dropped; 06aa2f4 filter: undrawn bosses
  invisible, ghost cues shown; boss box shape along the horizon; pogo margins per time in phase; 387ff86 VE rage
  scoring; VE bell targets (off); 52d0e1e late-tick catch-up (skipped STATEs through the perception path);
  0f4435d finer/narrower time slack for tracked bells; 5cdf73f VE targets only attack bells; e77c6ec touched drop
  bells get their path back once the track rules a tink out; ec62558 a cue always starts a new attack (the run's one
  real unpredicted hit), unpredicted accounting with forecast gaps.
- Held-out recall (ve_dust + noise seed 7, margin 0, lags 2-4) 23,896 / 23,896 after every step.
- Main degraded_dust run on 52d0e1e (20261002_232157): 154 valid, 126 CLEAR (81.8 %), 0 WOULD_DIE, 2 HARNESS_FAIL.
  QUITs: rage drop-bell pattern 15, bursts 8, charges 3, 2 hits on skipped frames.

## Results (no job running)

- Oracle regression on ec62558 (20261003_014409): 66 eps, 65 CLEAR (98.5 %), 0 WOULD_DIE, 0 unpredicted; plus
  20 / 20 CLEAR on d4a85c5 (20261003_013226, stopped to move to the final commit).
- degraded_dust on ec62558 (20261003_022259): 61 eps, 47 CLEAR (77.0 %), 0 WOULD_DIE, 0 unpredicted.
- Nothing of this task is running. Instances 0 and 1 are left running idle (lead: launcher --restore). The live
  worktree C:\ssbot\live_vv (detached at ec62558) can be removed with `git worktree remove C:\ssbot\live_vv`.
- Tools: combat_run summary <run>; C:\ssbot\sandboxv_scratchec_stats.py <run> (hits by Control state from
  the recordings); hits_summary.py <run>; unpred_dbg.py <run> <inst> <ep> <hit f>; dbg_support2.py (support per x
  and height around a frame); touch_count.py; slack_need.py.

## Next

1. Rage drop-bell pattern (15 of 28 QUITs): the cue's +-0.1 s time slack (13 self-template placements per pending
   bell), the VE margin on bells (the boss-noise part does not apply to tracked bells, but the planner's hull
   sampling assumes one dilation), no pogo / redirect escapes in VE (drop-bell targets need a tink model: keep the
   untouched and tinked branches instead of withdrawing; simulate must be vectorised first).
2. Bursts (8): PREPARE 4.5 u beside the burst is where the attack bell lands and rolls out; the VE slack change
   (0f4435d) halves the bells' smear - measure live (needs a chunk on ec62558).
3. Dig In / Charge End pogos (0.2 pogo hits per charge vs 0.97 oracle): Charge End left/right margins 2.5 u.
