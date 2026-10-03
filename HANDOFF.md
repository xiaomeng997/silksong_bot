# HANDOFF — Task W (Forum movement kinematics, Reaper attack shapes, safe-pocket tool)

Stopped 2026-10-02 ~21:15 local: the plan's 5-hour usage window reached 92 % (stop rule). Worktree
`C:\modeling\silksong_bot\.claude\worktrees\wf_946a7803-63c-3`, branch `worktree-wf_946a7803-63c-3`. Everything is
committed. No job of mine is running (the excitation probe was stopped, input released on instance 3).

## Done (committed)

- **Model** (`brain/ssbot/knowledge/kin_jit.py` "Forum loadout", `kinematics.py`): `HeroParams.abilities` bits switch on
  wall slide / Ascendant's Grip cling / wall jump (lock, chain, queued interrupt) / wall slash (Reaper slowdown) /
  up-slash shove / Wall Scramble / Drifter's Cloak glide (Umbrella Float FSM) / dash + sprint FSM / Reaper down slash
  (Crest Attacks FSM) / hard landing, from HeroController 1.0.30000 and the hero's PlayMaker templates (dumped with
  UnityPy from `heroloading_assets_all.bundle` + `fsmtemplates_assets_shared.bundle`). 6 new modes, 22 new rows, 66 new
  params. Abilities 0 = Hunter, bit-identical (all 47 kinematics/knockback tests, planner and forecast tests pass;
  full suite 794 pass, 1 timing-budget test of hitbox_tables failed under the gate's CPU load).
- Estimator / tracker for the new rows (`forum_mode`, `ForumRows`, `Trace.wall`), kin_check categories
  (wall, glide, dash, reaper_down, scramble, hard_landing) and `--lanes bounds_ft`.
- Wall contact timing fixed against live data: a wall touches one physics step after first contact
  (OnCollisionStay2D, not Enter) — the test recording's jump-into-wall window then matches the log to the mm.
- `knowledge/1.0.30000/attacks/{reaper,hunter}.json` + loader `ssbot.knowledge.attack_shapes` + builder
  `tools/attack_table_build` (`--live` folds per-frame slash.dump samples) + audit `tools/attack_hit_audit`
  (Hunter 171806: normal TP 15/FP 0, up 18/0/FN 1, alt 6/0/FN 1).
- `tools/coverage_map` (safe pockets; tested on Bell Beast 171806: left gate inner wall top clearance 1.91 u),
  `tools/kin_fit_forum`, `tools/kin_bench_forum`, probes `room_scout`, `kin_excite_forum`
  (setup, `--setup-bb`, `--kinds`, `--random-dir`, `--attack-frames`), encounter `BellBeastReaper`.
- Facts: `docs/facts/1.0.30000/movement_kinematics.md` (Chinese; sections 1-4, 6; section 5 "实测" still empty).

## Measured so far

- Test recording `C:\ssbot\data\runs\m2\kn_excite_forum_test\2026-10-02\TRAIN\kn_excite_forum_s98990` (6 wall trials):
  cling vy exactly 0 (302 frames); slide vy change after the stick time -24 /s per frame (LateUpdate) plus -7.2 /s from
  gravity scale 0.1 (air hang started during the slide), as modelled; wall jump vx 25, 23.88, 22.77 ... and back to
  8.25 after ~9 steps (the lock ends with the jump's CancelJump, not after 15 steps), as modelled. kin_check (before the
  contact fix): plain 100 %, wall 90.6 % within 0.1 u at 0.5 s. On a lone instance every frame is 0.01665 s, which
  drifts the physics phase past the lanes' alpha margin (use `--lanes bounds_ft`).
- Partial fit run A (stopped at trial 125 of 170 + 40 attack-frame trials not reached):
  `C:\ssbot\data\runs\m2\kn_excite_forum\2026-10-02\TRAIN\kn_excite_forum_s98000` (recorder killed: meta not closed;
  the reader rebuilds a missing index). Seeds used: 98000, 98990.
- Bench (512 x 48, threads 4, under the gate's load): Forum nominal p50 1.95 / p99 2.49 ms, Hunter 0.99 / 1.94 ms.

## Savestates (C:\ssbot\sandbox\savestates, prefix kn_)

`kn_forum_wall` (Hang_06 platform x 80 y 12.59, wall face x 83.0 to the right, Reaper + Wallcling + Silk Spear,
Swift Step / Cling Grip / Drifter's Cloak / Clawline, no double jump, no Silk Soar), `kn_forum_floor` (Hang_12 floor
x 32-64, same loadout), `kn_bb_reaper` (Bell Beast arena, Reaper + Silk Spear: encounter BellBeastReaper),
`kn_hang06_wall`, `kn_hang12_floor`, `kn_lib11_shaft` (unused), `kn_scout_*` (copies of community states).

## Next (in order)

1. Excitation, instance 3 (port 47020), from this worktree at HEAD, `NUMBA_NUM_THREADS=4`:
   - A wall fit: `..\scripts\uv.cmd run python -m ssbot.probes.kin_excite_forum --instance 3 --savestate kn_forum_wall
     --wall-x 83.0 --x-safe 76.8 83.2 --seed 98010 --trials 170 --attack-frames 40 --kinds
     "wall_hold,wall_hold,wall_jump,wall_jump,wall_attack,wall_attack,wall_scramble,reaper_attack"` (~35 min); the
     stopped run s98000 can serve as part of the fit set.
   - B wall held-out: same with `--seed 98100 --trials 120 --attack-frames 0`.
   - C floor fit: `--savestate kn_forum_floor --x-safe 33 63 --random-dir --seed 98200 --trials 160 --kinds
     "glide,glide,dash,dash,reaper_attack"`; D floor held-out `--seed 98300 --trials 100`.
2. `tools/kin_fit_forum <A> <C>` (clip phase lengths: glide antic / inflate / deflate, Reaper down slash antic /
   slash, scramble antic / end, air sprint; writes `knowledge/1.0.30000/kinematics/hero_reaper_forum.json`), then
   `tools/kin_check <B> <D> --params hero_reaper_forum.json --lanes bounds_ft` (acceptance: hull >= 99 % per category);
   diagnose misses with the window roll-out (as in this session: model vs log frame by frame).
3. Reaper shapes: `tools/attack_table_build --crest Reaper --live <A>/attack_frames.jsonl`; then a Bell Beast Reaper
   data run for hits: `..\scripts\uv.cmd run python -m ssbot.tools.combat_run run --instances 3 --encounter
   BellBeastReaper --mode data --hours 0.5 --seed 98500` and `tools/attack_hit_audit <run> --crest Reaper
   --instances 3` (check the Reaper swing clip names first: the audit takes the down slash from "v3 Down Slash").
4. Fill section 5 of the facts file; not modelled yet: Mantle (翻越), down dash, scuttle, sprint jump, Clawline.
