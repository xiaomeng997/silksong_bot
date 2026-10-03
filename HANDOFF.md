# HANDOFF — Task W (Forum movement kinematics, Reaper attack shapes, safe-pocket tool)

Round 2 finished normally 2026-10-03 ~00:30 local. Worktree `C:\modeling\silksong_bot\.claude\worktrees\wf_946a7803-63c-3`,
branch `worktree-wf_946a7803-63c-3`. Everything is committed; no job of mine is running (instance 3 idle, input
released). A detached live worktree `C:\ssbot\live_kn_7a56ead` (at this branch's commits, numba warm) was used for the
live runs; keep or `git worktree remove` it.

Facts: `docs/facts/1.0.30000/movement_kinematics.md` — section 1.6 (template-disabled actions), corrected 1.2-1.4b,
section 5 (fit, held-out acceptance, Reaper samples + hit audit, bounds_ft decision), section 6 (bench).

## Done this round

- Live data on instance 3 (seeds 98010, 98100, 98200, 98300, 98400, 98410, 98500), all under
  `C:\ssbot\data\runs\m2\kn_excite_forum\2026-10-02\TRAIN\kn_excite_forum_s<seed>` except the Bell Beast Reaper data
  run `C:\ssbot\data\runs\m2\20261002_225836_BellBeastReaper_data` (9 fights).
- Model fixes (kin_jit / kinematics, all behind `HeroParams.abilities`; Hunter rollout unchanged, 58 kinematics /
  knockback / coverage tests pass, full suite 794 pass + the known CPU-load timing test of hitbox_tables):
  template-disabled actions (Reaper antic), Reaper terrain thunk (phase 4), FinishDownspike vy -10, Wall Scramble
  OnEnter force / End decel / brake / Hit Roof + Detach, up-slash MovePosition one step late (row SHOVE), glide
  Inflate velocity (UmbrellaWindObject own speed), dash end with the sprint's accel, Ground Sprint Translate from the
  drawn position (rows RX0/RY0), sprint grace / skid, air sprint clamp lag, RegainControl's queued jump (row JBUF);
  estimator: wallSlashing, wall-lock unlock, air hang from step-start velocity, wall contact from terrain, FixedUpdate
  entry timers, pending OnEnter changes, glide press spends the jump queue.
- `knowledge/1.0.30000/kinematics/hero_reaper_forum.json` (kin_fit_forum on s98000 + A + C).
- Held-out acceptance (B + D, bounds_ft lanes): covered 99.69 %; wall 99.90, scramble 100, dash 100, plain 100,
  contact 100, glide 98.95, reaper_down 98.78 (both < 99 %: see facts 5.3). kin_check now has `uncovered:slope`.
- Reaper table (`knowledge/1.0.30000/attacks/reaper.json`): normal / alt / up / wall / charge live frames;
  down src "DownSlash New". Hit audit (slack 0): normal 103/22/0, alt 17/1/0, up 34/2/0, down 17/2/1 (TP/FP/FN);
  the 22 normal FPs are all in 5 Bell Beast states (Attack Burst, Charge Emerge, Rage Roar, Charge Loop, Leap End).
- Oracle: `slash.dump` optional `paths` (dumps FSM-swung objects). Built with `-p:Deploy=false`, NOT deployed.
- Tools: `kin_window` (one window model vs log), `kin_fit_forum` rewritten (phase ends from the log, boundary rule),
  `attack_table_build --live` (several files, charge from the release, drops inactive-object samples),
  `kin_excite_forum` (`--attack-kinds`, dash_attack, charge, object-active flag, `paths`).
- bounds_ft decision (task item 4): not for the planner (p95 hull 0.006-0.17 -> 0.35 u for +0.2-0.6 pp); keep for
  kin_check / the residual monitor. Facts 5.5.

## Needs the lead

- Deploy the oracle (SlashDump `paths`), then on instance 3 from this branch:
  `..\scripts\uv.cmd run python -m ssbot.probes.kin_excite_forum --instance 3 --savestate kn_forum_floor --x-safe 33 63
  --random-dir --seed 98420 --trials 0 --attack-frames 40 --attack-kinds "reaper_attack,dash_attack"` (down slash and
  dash attack polygons / frames), then
  `..\scripts\uv.cmd run python -m ssbot.tools.attack_table_build --crest Reaper --live <A>/attack_frames.jsonl
  <s98400>/attack_frames.jsonl <s98410>/attack_frames.jsonl <new>/attack_frames.jsonl` and re-run
  `tools/attack_hit_audit C:\ssbot\data\runs\m2\20261002_225836_BellBeastReaper_data --crest Reaper --instances 3 --slack 0`.
- Hunter estimator note (not changed, Hunter must stay bit-identical): `_replay_gravity` uses the frame's own vy for the
  air-hang check while GS comes from the exported gravity scale, so at a jump apex with the button held the estimate
  can say "hang done" one step early (Forum path fixed with the step-start velocity).

## Next (in order)

1. Glide (98.95 %) and Reaper down slash (98.78 %) residuals: 12 + 12 windows (facts 5.3); `kin_window` on them.
2. Reaper dash attack movement (Sprint FSM Reaper Antic / Upper / End: 50 u/s forward, x0.85, CurveFloat vy, End vy 7)
   is not modelled; the probe's dash_attack trials (s98400) recorded it.
3. Mantle (scramble past an open wall top: Mantle Antic rays, Mantle Shift MovePosition +0.4 / +1.35, To Air bounce)
   and the air mantle — needs a wall with an open top (kn_forum_wall's top is under a ceiling, which takes the Hit Roof
   path, as the Forum left wall should); Clawline not started.
4. Slopes: the rollout does not collide `Terrain2D.slopes`; check the Forum arena's terrain for them before trusting
   pocket plans near its ceiling step.
5. Boss "does not take hits" states for the hit predictor (the 22 FPs), cross-checked on Hunter data.
