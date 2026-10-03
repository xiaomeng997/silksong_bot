# HANDOFF: task V (Bell Beast in the vision-equivalent view)

Worktree C:\modeling\silksong_bot\.claude\worktrees\wf_946a7803-63c-1, branch worktree-wf_946a7803-63c-1.
Findings: docs/facts/1.0.30000/m2_vision_view.md (round 2 section at the end).
Live runs go from a separate detached worktree C:\ssbot\live_vv (git worktree of this branch, checked out at the
commit under test, numba prewarmed with planner_bench). Instances 0 and 1 (ports 47017 / 47018) were restarted by
this task at 22:2x (launcher -n 1 --first 0/1 --detach); the lead runs launcher --restore.

## Done (round 2)

- bb568e5: no logged velocities in the vision view (vision/track.VelocityTracks: slope of the detections), cues get
  detection noise and misses; drop-bell x = mean of its cue detections, burst anchor = mean of the burst cue.
- 71f2478: attack bells on exact paths from their tracks (bell_track.AtkBellTracks; registry AtkBell start); a burst
  whose two bells are tracked drops its attack-bell unions (Burst Recovery, tail).
- 06aa2f4: filter: undrawn types with a renderer have no image extent (the "Antic Bell Shaker" made the underground
  boss visible), a ghost's due cue in the image shows (boss lost at the edge); boss box shape along the horizon
  (SHAPE_T); pogo-gate margins per 0.1 s of time in the phase (phases_tau in BellBeast_vision_box_margin.json).
- 387ff86: VE rage scoring p 0.5 within 10 HP above the rage HP; VE bell targets implemented, off (SSBOT_VE_TARGETS=1).
- Held-out recall (ve_dust + noise seed 7, margin 0, lags 2-4) 23,896 / 23,896 after every step.
- Live: bb568e5 7 eps (4 CLEAR); 71f2478 28 eps, 21 CLEAR (75 %), 0 WOULD_DIE.

## Running / pending

- Final degraded_dust run on 387ff86 (started 23:14 PDT, instances 0,1, seed 90400, --episodes 85 --hours 3.2):
  run dir C:\ssbot\data\runs\m2\2026100?_*_BellBeast_eval_planner_degraded_dust (the newest; log
  C:\ssbot\sandbox\vv_scratch\live_387ff86_final.log). Then the oracle regression (>= 60 eps, --view oracle).
- Stop gracefully: cd C:\ssbot\live_vv\brain; ..\scripts\uv.cmd run python -m ssbot.tools.combat_run stop <run dir>
- Summaries: combat_run summary <run>; C:\ssbot\sandbox\vv_scratch\rec_stats.py <run> (hits by Control state from the
  recordings, pogo hits per charge); hits_summary.py <run> (decision rows before each hit).

## Next

1. Bursts in VE (3 of 7 QUITs on 71f2478): the PREPARE stance 4.5 u beside the burst puts the hero where the attack
   bell lands (x' 3.15) and rolls out at 12 u/s; with the VE margin the jump-over / step-in windows close. Try a VE
   stance and det-bell margins without the boss-noise part (the bells carry their own skin).
2. Rage drop-bell pattern (Ptn L/R, 3 QUITs): self templates before the fall (cue +-0.1 s time slack, both sides);
   VE bell targets for pogo escapes exist (off) - evaluate live, or a tighter pre-fall model from the cue.
3. Dig In / Charge End pogos: still 0 accepted in VE (L/R margins 2.5 u at Charge End from the charge's deceleration
   timing; Dig In top 1.5 u).
4. The VE HP count misses hits (80 vs 75): find which hits the filter drops.
