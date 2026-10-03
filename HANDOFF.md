# HANDOFF: task V (Bell Beast in the vision-equivalent view) - stopped by STOP_AGENTS

Stopped 2026-10-02 21:04 PDT: C:\ssbot\sandbox\STOP_AGENTS ("lead: 5-hour window at 86 % ... Resume after 22:40 PDT").
Worktree C:\modeling\silksong_bot\.claude\worktrees\wf_946a7803-63c-1, branch worktree-wf_946a7803-63c-1.
No live run of mine is running (the two combat_run workers ended after their episode on the stop file).
Instances 0 and 1 are left running (not touched otherwise). Findings: docs/facts/1.0.30000/m2_vision_view.md.

## Done (commits da9a232, a479c09, 2068293, 7c18e6c + this one)

Diagnosis with the new tool `ssbot.tools.view_compare` (oracle vs degraded_dust on the same recorded fight,
recorded masks as the prefix): the vision view never generated a pogo because the hurtbox table was built relative to
the root transform but placed at Entity.pos (charge box 2.35 u low, under the floor); falling drop bells had only
their self-template union (exact paths were oracle-only: FSM + logged velocity); the rage underground kept every
attack in support (FORCED_RISK through Rage Pos / Rage Antic); the attack start came from the dust cue +-0.1 s and a
fit over standing frames.

Fixes (all vision-legal; see the facts file for the numbers):
- combat/bell_track.py: drop-bell path from its detections (column x, drop time from the known fall curve, bounce side
  once the drift is significant), two branches until then; withdrawn on a hero attack in reach or a track off the
  model. Forecaster VE uses it (Forecast DetBell with t0 / sides / skin); Forecast.committed keeps exact bells.
- hurtbox table rebuilt relative to Entity.pos, "recover" split by family (BossTracker.shape_key).
- VE attack start re-anchored at every drawn phase entry; AttackFit off by default (planner_policy.FUSION).
- BossTracker.fused_pos: box position averaged over the attack's detections moved along the mean path.
- Pogo gate in VE (Forecast.certain_boss + planner buckets): the boss shape eroded by measured residuals
  (boss_path_audit --view degraded_dust --margins -> knowledge/1.0.30000/enemies/BellBeast_vision_box_margin.json),
  valid until the phase can end.
- Rage? -> Rage Pos only when P1, not raged, HP <= 75 (311/311 logged; 0/1990 above).
- kinematics.rollout: writable events/dt/fs (read-only broadcast view = second numba specialization = the mid-fight
  compile of fresh worktrees); warmup on a TERRAIN-message arena + clip_fractions (sigs check: no new specialization
  in 3000 replayed frames, both views).
- Tools: view_compare, bell_track_audit, boss_path_audit --view/--margins, support_recall --noise-seed.

## Measured

- Held-out recall (support_recall i2_002/i3_002, held-out tables, lags 2-4, margin 0): oracle 23,896/23,896;
  ve_dust + SimpleNoise seed 7: 23,896/23,896 (1,652 drop-bell contact frames).
- Replay ep2 of 20261002_171806 i0 (view_compare): VE FORCED in Rage Antic 100 % -> 1.4 %, Rage Pos 57 -> 0 %,
  Burst Antic+bell 100 -> 0 %, Submerged+bell 36 -> 9 %; VE pogos accepted in Charge 0 -> 0.55 per tick with the
  certain-box gate (2.28 with the nominal box, oracle 3.0); Dig In / Charge End pogos still blocked (recover margins
  2-5 u: Dig In sinking).
- Live 7c18e6c degraded_dust (20261002_205247, instances 0/1, seed 90000): 2 episodes before the stop: 1 CLEAR,
  1 QUIT (DropBell M2 hit). tick p99 12.4 / 12.8 ms.

## Next

1. Replay the M2 hit of 20261002_205247 i0 ep0 (postmortem / dbg scripts in C:\ssbot\sandbox\vv_scratch:
   dbg_support.py lists which placements / exact bells cover the floor at a frame) - was the bell on its exact path
   or back on the self template (touched / deviation), and what made the plan FORCED.
2. Live degraded_dust on instances 0,1 (>= 150 valid episodes; seeds 90000-94999; e.g. --seed 90100 --hours 1.5 per
   chunk), summarize with combat_run summary + fight_stats; oracle regression chunk (--view oracle, ~40 eps).
3. If bursts / attack bells cause hits: an attack-bell track model like bell_track (launch from the burst, vx +-1,
   vy 38, first bounce vx +-12 vy 14).
4. Dig In / Charge End pogos in VE: the recover margins are dominated by Dig In's sinking (table bins); a per-state
   shape timing would shrink them.

## How to resume

    cd C:\modeling\silksong_bot\.claude\worktrees\wf_946a7803-63c-1\brain
    ..\scripts\uv.cmd run python -m ssbot.tools.combat_run run --instances 0,1 --encounter BellBeast --mode eval
        --policy planner --view degraded_dust --threads 4 --seed 90100 --hours 1.5 --episodes 400 --real-quit 0.2
    ..\scripts\uv.cmd run python -m ssbot.tools.combat_run summary C:/ssbot/data/runs/m2/<run>
    ..\scripts\uv.cmd run python -m ssbot.tools.combat_run stop C:/ssbot/data/runs/m2/<run>      # graceful stop
Long offline jobs: C:\ssbot\sandbox\vv_scratch\bg.ps1 (below-normal priority, NUMBA_NUM_THREADS=4).
