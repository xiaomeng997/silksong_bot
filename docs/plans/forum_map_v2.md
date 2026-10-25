# Forum map v2 - the consolidated design (2026-10-24)

THIS FILE: the one complete design document the person asked for on 2026-10-24 ('there are so many commits for the
same feature - we need one complete design document, otherwise things get missed or contradict each other'). It
replaces the incremental spec that grew here by 69 commits (9603ecf .. deb8c9f; the history stays in git:
`git log -p -- docs/plans/forum_map_v2.md`) and folds in the stage reports. Every rule, number and decision appears
ONCE, in its final form; superseded / withdrawn / analysed-not-built items appear only in the decision log (section 5),
one line each; where the sources disagree or leave a gap the item is listed in section 6, not decided here.
C:/ssbot/data/m2_play/map2/design/disposition.txt maps every paragraph of the old spec (deb8c9f) to its place here.

SOURCES (tags used below): [spec] the old spec, docs/plans/forum_map_v2.md at deb8c9f; the HANDOFF.md stage sections of
worktree .claude/worktrees/wf_f1846551-5f9-1 (branch worktree-wf_f1846551-5f9-1) - [M0] .. [M3], [M4a], [M4b], [M4c],
[M4d], [M4d2], [S1], [S1b], [G], [T1], [T2], [T3] (the same stages in docs/facts/1.0.30000/forum.md 91 - 105: M0 91, M1
92, M2 93, M3 94, M4a 95, M4b 96, M4c 97, M4d 98, M4d2 99, S1 100, S1b 101, G 102, T1 103, T2 104, T3 105), [SP3] its
'Task 1v1 - stage SP3' (forum.md 67); [T4] the worktree's commits 29ae48e, b2c9cf0, a2cf22b, 499df40 (2026-10-24 11:08 -
12:40), its uncommitted library header and C:/ssbot/data/m2_play/map2/a1n/t4 - INTERIM, T4 has no PROGRESS / HANDOFF
entry yet; [code] the worktree's code at 499df40 (brain/ssbot/map2/*.py); [GATE] C:/ssbot/data/m2_play/map2/M4_GATE.txt;
[P-m4] / [P-a1n] / [P-ev] map2/m4/PROGRESS.txt, map2/a1n/PROGRESS.txt, map2/ev/PROGRESS.txt; [RFX] reflex/REPORT.txt,
[RFX2] reflex/stage2.txt; [AC1] airceil/stage1.txt, [AC2a] airceil/claim/claim_report.txt, [AC2b]
airceil/recs/stage2b.txt, [AC3] airceil/verify/stage3.txt; [MOVES] C:/ssbot/data/m2_play/MOVES_TODO.txt; [OLD]
docs/plans/forum_planner_plan.md (the person's notes of 10-19 / 10-20 are in its long notes line 252).
CODE REVISIONS OF THE NUMBERS: each number carries its stage tag; the gate ran the frozen checkout c0329d2 (S1 + S1b),
T3 measured f27ac9c (frozen checkout C:\ssbot\live_1v1_f27ac9c); the worktree head is changing under T4 (engine revisions
t4b - t4d) and its numbers are interim until T4 reports.

CONVENTIONS: u = world units, her box centre / the Clapper's transform x, centre to centre unless a box edge is named
(1 u ~ 2.2 Hornet widths); bb = her box bottom above the floor (floor y 3.015); frames = game frames (60 fps; a
hit-stop freeze is not a frame); steps = 50 Hz physics steps (some frames have none); P = the first frame whose
latched ACTION mask (STATE act.mask) holds the key (M0's convention - two frames later than SP13's P); j = a
Clapper's frame in its state; AS = the air sprint's entry frame; k = frames from the decision / before an event.
STATUS MARKERS: [ON] built and on in the live arm `m2`; [OFF] built, behind a switch off by default or not wired;
[OFFLINE] an offline tool / analysis only; [DESIGNED] designed, not built; [RUNNING] in a stage now in progress.
Attributions '(the person, date)' mark the person's ideas and decisions; '(the lead, ...)' the lead's.

---------------------------------------------------------------------------------------------------------------------

## 0. 中文摘要（给你）

这份把原 spec 的 69 次提交和各阶段报告合成一份，取代原来的增量 spec：每条规则、数字、决定只出现一次（最终版）；
被替换、撤回、分析后不做的只在第 5 节"决定记录"里各占一行；来源之间有矛盾或缺口的列在第 6 节，没有替你拍板。

| 部件 | 现状 | 下一步 |
|---|---|---|
| L1 Clapper 模型 | 做好、map2 开着就在用；录像里 92-93 % 能找到真实分支；叠加层眼看一直没做 | 你定：下次实机前还要不要眼看（Q1） |
| 主角模型 HERO2 | 做好，默认关，map2 会打开它；928 次实测 899 次误差 < 0.1 u | 下劈恢复锁、冲刺侧面接触等几处待实机探针 |
| M1 包络引擎 | 做好、在用；随机按键 0 次逃出包络 | — |
| A1_n 递归表 | 做好、和引擎逐帧一致；开关默认关。T4（10-24 下午做完）修了验证者的 20 条后，开表的搜索在离线实测里第一次领先：1 秒内找到的招 164→183、156→181，0.25 秒 76→87；回放里 w7 掌控 33.1%→35.3%，0 碰撞、0 无效按键。但 0.15 秒的短决策仍落后，长查询（多动作长时间）开了更差 | 实机开不开表你定（Q5）；冻结代码 live_1v1_499df40 |
| 搜索 L3 | 做好、在用；w7 第一个安全计划 p90 119 ms；1 秒约达 60 秒价值的 75 % | 评估加速（逃生漏斗、每招每帧危险、窗口形状）；T4 已有漏斗和 eps(k) 的中期试验 |
| 实机控制 | 做好（SSBOT_FORUM_MAP2，默认关）；回放审计 0 碰撞；w7 掌控约 33 % | 交接（丢计划规则、动作中途重规划、半途出招时的兜底、没预测到的钩子反应）；"计划当管道"算不算在 E2 里，来源不一致（Q24） |
| 评估/交接流程 ev | 脚本已写好，还没启动（只写了进度文件的开头一行）：等 T4 结束、你看过这份文档再启动 | E1 先读 T4 的漏斗和 eps(k) 中期结果、在其上继续（Q20 已定） |
| 反射层 | 表做好（427 万格），默认关、没接进 bot | 你定的：只留搜索来不及的窗口（约 1 %） |
| 长期站位规划 | 只有设计 | 在顺序里的位置待你定（Q12） |
| w7 闸门（10-23） | 没过：跑 2 局，0 局无伤；5 次掉血时按键都是默认规划器的，3 次紧跟 map2 丢计划 | 评估和交接做完后你决定下一次闸门 |

你 10-24 的答复已写进第 6 节：不做眼看、直接测（Q1）；map2 要有保底方案（Q2）；递归表实机打开、是主力（Q5）；
不落地演示不算 map v2 的目标（Q21）。Q3 的解释和建议、Q12 的顺序建议见第 6 节。
Q20、Q22、Q23、Q24、Q27 是事实性问题，负责人已据实回答（见第 6 节）。快速反应部分按你 10-24 的意见改成"自动生成的固定套路"（3.5）。

---------------------------------------------------------------------------------------------------------------------

## 1. Goal and acceptance

### 1.1 The goal

The person's decision (2026-10-20): stop adding hand-written tactics; build the map now. The moves of 1.2 must be
FOUND BY THE SEARCH from primitives and models, not scripted. The map has three layers (the person's design of
2026-10-19 / 20 [OLD]): L1 the enemy model, L2 her reach, L3 the search; plus the live control that executes the
search's plans, the reflex for the search's latency gap, and the long-term positioning planner (section 3).

### 1.2 The five moves and the regression (the person, 2026-10-20 [MOVES]; with M0's corrections)

- P1 THE CLAWLINE IN EVERY STATE:
  - an IDLE Clapper reacts in the needle's hit frame (P + 8 / 9) and picks its move from her position at the hit - still
    her throw position [M0]: inside Slam Range the close list (slam -> the strike windows; cast -> head pogos; evade ->
    the chase / a second hook), beyond it the far list (jump -> the ride; jump cast -> its head / its flight with the
    exit through the burst; cast -> pogos).
  - the person's three hook cases (2026-10-22 [MOVES]): (a) a near hook that draws a slam: the Clawline is pressed at
    antic ~-9, control comes ~22 - 30 f before Slam 0, and the first window (the down slash on Slam 0 at antic ~47)
    must be reachable, with an umbrella in between; (b) a far hook (beyond Slam Range): she is at its face before Jump
    Aim, so it jumps nearly in place and she RIDES it; the jump SLAM - fly low, only the landing hammer matters (7.1 u
    at 4.1 u in front, nothing past 7.76 u, behind the landing free), come down over / behind the landing or pogo its
    head there; the jump CAST - fly high, stay above the dome or float down over the landing point / pogo the caster's
    head (4 - 4.8 u) through the burst (the pogo i-frames also block it); (c) the hooked Idle Clapper EVADES: Clawline
    again from control + 12 / 13 - it hooks it in its new antic (not Idle: a free hit, no reaction).
  - EVERY ANTIC: the slam - a Clawline press by antic ~11 (at antic 5 - 11 it reaches the first window, at 0 - 4 /
    earlier the second); the cast - any time, free (no reaction during a cast); the jump antic - the take-off hook.
  - the other Clapper locked by the buddy rule = a free hit.
- P2 the umbrella close -> drop -> strike, the close frame chosen by the search.
- P3 THE FACING STEERED BY THE CONTACT SIDE (the person, 2026-10-19 [OLD]): every move's start state turns to her, so
  the side of its axis she is on at the contact frame decides its next facing; keep it facing the wall so its evades go
  to the middle (its back never near a wall: no escape jump) while she stays inside Slam Range (no far jump); cross to
  the middle side in a slam antic.
- P4 ride a jumping Clapper up (down slashes on its rising body at the 18 f cadence; side contacts bounce fully) and float
  down over / behind its landing (the big-rune dome is ~3.45 u high over the landing point). Once up high nothing
  reaches her for a while.
- P5 (LANDPOGO) a Clapper standing on her landing spot -> down slash it instead of landing on it.
- REGRESSION: the search must rediscover the known scripts in their own situations - CLAWSTRIKE (hop + Clawline at
  antic 5 - 11 + down slash on Slam 0), SLAMSTRIKE (the slam playbook's strike), JUMPTRAP (the pass under the trapping
  jumper), LOWHOP (the low hop over the bombs).

### 1.3 What 'found by the search' means

- Primitives + the generic strike module only: the combo library must NOT contain P1 - P5's own macros in the
  acceptance run; the suite runs twice - primitives only (the real test) and with the library (speed / quality)
  (the lead, 2026-10-20).
- Report per move: found same / found different (another plan chosen, a safe plan with the move's label found) /
  not found with the reason (missing primitive, missing mechanic, horizon, timing grid, infeasible, reaction not
  predicted, conditions, timeout) / found but fails live (model error).
- The suite (`brain/ssbot/tools/m3_accept.py`; data C:\ssbot\data\m2_play\map2\m3) [M3]: 236 situations (forced 63,
  the person's 30 slam strikes of 10-15, 143 from the SP14 / SP-AIR1 recordings, half within 120 f before an HP loss);
  recognizers per move (`recognize.py`); reaction labels on every outcome: P1-idle-slam = the first window (a down
  slash contact in Slam 0 / 1 or Slam Antic j >= 44; '+umb' when the umbrella opened between control and it),
  P1-idle-slam2 = the second window (j 20 - 43), P1-idle-evade (a second hook), P1-far-jump (the JUMP ridden),
  P1-far-jcast (the JUMP CAST struck, the outcome safe). 279 move cases in M3's and T3's tables, 275 in M4a's / M4b's
  tables of the same M3 v4 run (Q25).
- At which budget 'found' counts is not fixed (Q3).

### 1.4 The person's gates and done criteria

- THE w7 GATE (the person, 2026-10-22 ~11:10 PDT: 'test the map live - if the win rate is 100 % it is right and you
  continue; if there is a problem, stop and wait for me to look'; a win = the Clapper killed with no HP lost). As run
  [G]: 16 episodes on Forum_W_w7 (fo_cl_w7w), instances 0 / 1, 1.0x, arm m2; pass = 16 / 16 hitless kills AND map2 in
  control of >= 30 % of the engaged ticks (the lead added a 50 % bar on 2026-10-23 09:45; the person lowered it to 30 %
  on 2026-10-23 15:40); any problem -> stop, freeze, write M4_GATE.txt with every episode and a trace of each problem,
  no fixes - the person looks first. No stage after a passed gate (no M4f: the gate stops after its 16 episodes).
- ORDER BEFORE THAT GATE (the person, 2026-10-23 15:40): the safety items first (the press validity, the low side
  down slash out of the air sprint, the air dash restored after a pogo / hooked Clawline, the late-tick key slip),
  then the gate the same night; the reveal latency not required for it; the speed work after.
- THE SPEC'S OWN M4 CRITERION (2026-10-20): after the person's eye check, SSBOT_FORUM_MAP2 behind a switch, fixed
  points >= 90 % on P1 - P5 and the regression situations, then the w7 A/B (hitless; the air show) and the w13 A/B and
  the audit. Not reached; its relation to the gate is open (Q2).
- VALIDATE PREDICTIONS FIRST (the rule validate-predictions-first): frame accuracy per move on the recordings, then the
  person's eye check in the overlay before any live use. The overlay is prepared, never started [M2]; no source
  records the eye check as done (Q1).
- ENGAGED TICKS (the share's denominator): a Clapper observed, outside the battle's intro (the Clappers' and her Roar
  Lock) and a supervisor pause (`m4c_smoke.engaged_share`) [M4d2].
- The next live gate: the person decides after the evaluation / handover work [P-ev].

---------------------------------------------------------------------------------------------------------------------

## 2. Status (2026-10-24, ~14:40 PDT)

WHERE: everything on branch worktree-wf_f1846551-5f9-1 (not merged to main, not pushed); the reflex on branch reflex;
the no-landing query on branch airceil (from 9bff134). Frozen checkouts: C:\ssbot\live_1v1_c0329d2 (the gate's, S1 +
S1b), C:\ssbot\live_1v1_f27ac9c (T3; the tables library hard-linked in; the switch off by default; the switch off is the
gate's map2 with T1b / T2's hero bits and T2's engine key fixes [T3]). Arms (C:\ssbot\sandbox\1v1_arms.txt): m2 = the w7
default rnjb + SSBOT_FORUM_HERO2=1 + SSBOT_FORUM_MAP2=1; m2p the workers on the P-cores; m2p1 one worker; h2 = rnjb +
HERO2 (the control). Nothing live since the gate. The two table verifiers planned on 10-23 19:55 [P-a1n] ran on 10-24
~09:24 - 09:58 (a1n/review_exactness, a1n/review_search); T4 (their fixes) is [RUNNING] offline: commits 29ae48e ..
499df40 (11:08 - 12:40, engine revisions t4b - t4d, both libraries rebuilt 12:30 - the header not committed),
acceptance campaigns writing in a1n/t4/accept at 14:20 - 14:37, no PROGRESS / HANDOFF entry yet. The ev workflow
(started 10:50) has no artifact besides its start line in [P-ev] (Q20).

### 2.1 Components

| component | code | switch (default) | state | latest numbers |
|---|---|---|---|---|
| L1 Clapper model | map2/clapper.py, clapper_jit.py; knowledge clapper_m2.json, clapper_m3_margins.json | used whenever map2 runs | [ON] | realized branch found 92.2 / 93.4 / 92.4 % (fit / held / old sets); predict compiled, identical, 3 - 8x [M2, M4b] |
| the overlay (eye check) | map2/overlay.py; sandbox start_overlay_map2_clapper.ps1 | --overlay-map2 | prepared, NOT started | - [M2] |
| hero model HERO2 | kinematics.py / kin_jit bits | SSBOT_FORUM_HERO2 (off; MAP2 requires it) | [ON] in m2 | 899 / 928 hero-only trials within 0.1 u throughout, 0 worse with the last bit [T1] |
| M1 envelope engine | map2/envelope.py, env_jit.py | the search's envelope while the tables are off | [ON] | 0 escapes in 36,000 + 120,000 + 90,000 random rollouts [M1, M4a] |
| A1_n tables | map2/tables.py, bridge.py; tools t1_tables / t2_tables | search.Cfg.tables / LiveCfg.tables (off) | [OFF] - keep off live [T3]; T4 fixes [RUNNING] | exact; warm 4 - 6x faster than the engine; live smokes: map2's share LOWER (below) [T3]; T4: the verifiers' findings fixed in the engine and the tables alike, libraries rebuilt (t4d), not reported |
| search L3 | map2/search.py, strike.py, combos.py, recognize.py | Cfg.live() flags; T4 adds Cfg.exec_only (default on at the head, absent from c0329d2 / f27ac9c: the passes and exits keep to the bot's executable family - no up slash, free attack or hidden jump press), Cfg.shapes (off), Cfg.h_pass (the predictions reach the longest pass) [code] | [ON] | first safe plan w7 p50 / p90 / p99 65 / 119 / 951 ms [M4b] |
| press validity | map2/press.py | LiveCfg press_check, side_spr, free_pogo, ds_shrink, side_rule, spr_xvx, late_base (on) | [ON] | 0 invalid presses in 435 committed plans [S1b] |
| live control | map2/live.py; hooks in ForumPlannerPolicy / ForumPlanner | SSBOT_FORUM_MAP2 (off); LiveCfg switches (on) | [ON] in m2 | gate share 33.3 %; replay safety audit 0 collisions [G, T3] |
| reflex | map2/reflex.py, reflex_gen.py (branch reflex); clapper_windows_v2.npz | SSBOT_FORUM_REFLEX (off), NOT wired | [OFF] | 4,267,885 cells; precision 0.999 on 16,130 live presses [RFX] |
| window shapes (down slash) | map2/wshape.py | search.Cfg.shapes (off; tables on only; adds the shapes' windows to the predicate's) [T4] | [OFF] | exact against the judge; the search's predicate misses ~27 % [T2] |
| backward sets, dash bundle, flattened layer | map2/bridge.py; knowledge a1n_flat_v1_ev1_t120(_dash).npz | not wired | [OFFLINE] | backward: exact only without the float's inertia (Back.exact); flattened: an upper bound only up to Tables.valid_until [T4] |
| no-landing query | map2/noland.py (branch airceil, not merged) | search.Cfg.no_land (off) | [OFF] | the air show's ceiling ~74 - 86 % vs 38 % [AC2b, AC3] |
| combo library | knowledge/1.0.30000/enemies/forum/combos/*.json, combos.py | given to the search or not | built | CLAWSTRIKE, SLAMSTRIKE, JUMPTRAP, LOWHOP; no P1 - P5 macro [M3] |
| escape funnel, eps(k) | T4's scripts eps_fit.py, funnel_sits.py | - | [DESIGNED]; an offline trial [RUNNING] in T4 (interim, not reported) | eps(k) p99 at k 1 / 5 / 10 / 20 / 45 / 60 = 0.031 / 0.529 / 0.908 / 1.170 / 1.840 / 2.590 u (928 trials, 12,341 syncs); 18 situations: forward 120 / 180 f warm p50 ~5.1 / 9.1 ms vs the engine ~31.6 / 54.8, backward ~0.6 / 1.2 ms; vs the exit checks same 55, exit only 7, funnel only 1, both no 27; the valve fired once [T4: a1n/t4/funnel/eps.json, eps.log, funnel_try.json] |
| steering in the tube, the drop rule on a 1-frame shift, re-plan from mid-action | - | - | [DESIGNED] (ev E2; the tube: Q24) | - |
| long-term positioning planner, score field, aim nodes | - | - | [DESIGNED] | - |

HERO2 bits: M0 H2_GLIDE_GRAV, H2_REL_LOSS, H2_GLIDE_ATK, H2_INFL_END, H2_POGO_RS; M4a H2_JUMP_DCD, H2_SPR_ATK,
H2_SPR_JUMP, H2_DASH_END (kin rows ABUF, XVX); S1 H2_POGO_DASH 512, H2_CLAW_SPR 1024; S1b H2_SPR_FIN 2048; T1b
H2_SHUTTLE 4096 (kin rows SHUT, XVXD); T2 H2_LAND_DASH 8192. `SSBOT_FORUM_HERO2_OFF=<bits>` takes bits out (today
15872 = M4c's / M4d2's model, 12288 = S1b's = the gate's [T3]).

### 2.2 The latest measured numbers

(All of 2.2 up to T3's code f27ac9c; T4's changes at the head are not reported.)
- EXACTNESS. The A1_n tables against the M1 engine: T1 16 runs / 5,758 passes, T2 (with the air dash) 11 runs / 3,939
  passes, worst 2.6e-13 u; M3's 236 situations with the search's own danger 236 / 236 + 236 / 236, exit checks 673 /
  673, windows 69,874 + 37,056 equal; entry from 406 transitional states 1,218 / 1,218 without the dash, 1,217 / 1,218
  with it (one start 0.032 u short at frame 60) [T1, T2, T3]. Containment: 0 escapes in 118,500 + 50,100 + 118,500
  random 120 f rollouts [T1]. Tightness: 97.3 % of the floor targets (120 f) within 0.1 u, every miss after a
  Clawline [T1]. Switches off: the search's deterministic digests 130 / 130 + 106 / 106 and the bot's replays 24 / 24
  byte-identical [T3].
- THE ACCEPTANCE (279 move cases, same / alt / not; primitives only) [T3]: 200 work units 94 / 108 / 77 (202 found,
  tables on = off); 1 s off 89 / 70 / 120 (159 found), on 98 / 79 / 102 (177; run 2 166); 0.25 s off 60 / 20 / 199
  (80), on 53 / 25 / 201 (78). The 60 s reference (275 cases): v4 112 / 109 / 54, m4a2 113 / 101 / 61 [M4a]. P3-face
  is never found 'same' (0 of 14 in every run; 'alt' 0 - 2). The 1 s losses against 60 s are mostly the budget - the hook's reaction
  moves need the third depth and the contingent recombination [M4b].
- SPEED: the first safe plan on the recorded w7 one-Clapper situations p50 / p90 / p99 65 / 119 / 951 ms (split search
  over 2 processes, simulated load) [M4b]; T3's re-measure without the load: tables off 66 / 156 ms, on 84 / 206 ms (p50
  / p90; on is ~20 ms later). The live searches p50 92 - 104 / p90 184 - 205 ms [S1]. A 1 s decision reaches ~75 % of
  the 60 s value (w7: 1.64 vs 2.13). Two Clappers: first safe plan p90 423 ms, 1 miss in 95 [M4b]. Where a live
  decision's time goes: the envelope passes 26 % (1 s cap) / 32 % (0.25 s), the closed-loop evaluation ~50 %, the
  windows 10 %, the witnesses 8 %, the danger lists 7 % [T3]. TickCheck per frame w7 p99 1.3 ms [M4b]; map2 on the
  bot's thread p99 1.4 - 3.1 ms per tick; a commit check p99 7 - 25 ms [S1, S1b, G].
- MAP2 IN CONTROL (share of the engaged ticks): live in the gate 33.3 % pooled (903 / 2,709) [G]; strict replay w7
  32.6 % with the tables off, 23.0 % on, w13 4.5 / 2.5 % [T3]; the share falls ~9 points under a loaded machine [S1b].
- THE REVEAL LATENCY (a Clapper's move start to the first key of a committed map2 plan searched from a snapshot at /
  after it; strict w7): 64 of 84 move starts get one within 60 f, its first key p50 / p90 20 / 43 f (tables off)
  [T3]; the target (<= ~6 f to a plan that can press at antic 5) is not met. map2 pressed the Clawline into a slam's
  first window 0 times in every run (the fallback's slam script: 8 in M4d2's final strict w7 runs, 12 in S1's 3 runs,
  2 in the gate) [M4d2, S1, G].
- SAFETY IN THE REPLAYS: the audit (each control run's keys as sent, re-simulated in every outcome still possible)
  0 collisions in every T3 arm; the press scan 0 invalid presses in committed plans [T3].

### 2.3 The gate (2026-10-23 19:29 - 19:31 PDT) and its causes [G, GATE]

FAILED, stopped after the first episode on both instances: ep1 i0 a kill in 31.9 s with 3 HP lost; ep2 i1
QUIT_EMULATED (HP 1 after three hits), no kill; 0 / 2 hitless kills; share 33.8 / 32.8 %. map2's moves: 9 down slash
strikes, 5 hooks, 0 rides, 1 slam strike (no bounce), CLAWSTRIKE 0. 0 map2 errors. Every HP loss came while the
default planner had the keys (hit_fb 9 / 7). 3 of the 5 followed a map2 plan dropped 'fail:clappers' beside an
attacking Clapper: (P2, P5) both of map2's slam strikes were dropped at their planned contact frame because all 4
outcomes of each (timing view 'early' only) had Slam Antic -> Slam 0 one frame before the game, and the fallback,
handed a mid-slash state, jumped (umbrella, no bounce) / air-dashed into the lunge or the hammer; (P3) a hook on an
Idle Clapper whose slam reaction matched none of the plan's outcomes, dropped at the hook, the fallback floated into
the slam. 2 were the fallback's own (P1 a small rune bomb after a map2 hook ended beside the casting Clapper; P4 the
slam script + an air dash) - in 60 recent default w7 episodes only 1 had a hit before the kill [G open item 4]. Kill
time 31.9 s vs the default's 16 - 20 s. Late ticks 29 / 35 %. (Whether another worktree's reflex_build jobs ran during
the gate or were suspended: Q23.)

### 2.4 Stage history (the spec's stage plan M0 - M4 as run; details in the HANDOFF sections)

| stage | date | what | outcome |
|---|---|---|---|
| M0 | 10-22 | the hero model's calibration, 779 live forced trials on w7; HERO2 | the measured mechanics of 3.2.1; 466 / 484 trials within 0.1 u |
| M1 | 10-22 | the envelope engine (offline) | exact containment; cluster counts 1 - 2 orders above the estimate |
| M2 | 10-22 | the Clapper model, predict(), the overlay (not started) | 3.1 |
| M3 | 10-22 | the search, contingent plans, the acceptance suite (60 s) | 112 / 109 / 54 of 275; full search p50 19 s |
| M4a | 10-22 / 23 | live probes of the mechanics the plans lean on (420 hero + 220 Clapper trials) | the air dash's cancels, the restores, the hooked body, the sprint jump found |
| M4b | 10-23 | speed (compiled, identical results; anytime; split search; hard cap) | first safe plan w7 p90 119 ms |
| M4c | 10-23 | integration behind SSBOT_FORUM_MAP2 | works end to end offline; share w7 strict 5 - 11 % |
| M4d | 10-23 | 20 review findings (14 defects) fixed | possible outcomes, hook variants by control, Clawline facing |
| M4d2 | 10-23 | map2 in control, the reveal latency | share w7 strict 11 -> 31 %; latency not shortened |
| S1 / S1b | 10-23 | the safety fixes before the gate; two verifiers' 10 findings | press validity; 0 invalid committed presses; audit 0 collisions |
| G | 10-23 19:29 | the person's w7 gate | FAILED, 0 / 2 hitless kills (2.3) |
| T1 / T1b | 10-23 / 24 | the no-dash table library; the sprint jump in the hero model | exact; the closure does not converge |
| T2 | 10-24 | the air dash as the bridge; backward sets; window shapes | exact with the dash; the predicate misses ~27 % of windows |
| T3 | 10-24 | the tables in the search (switch, off) | exact, not faster live; keep off |
| verifiers | 10-24 ~09:24 - 09:58 | the two table verifiers (exactness, search) | findings fixed by T4 (no report of their own in the sources) |
| T4 | 10-24 ~10:07 - | the verifiers' fixes (engine + tables), libraries rebuilt, acceptance re-run, a funnel trial, eps(k) | [RUNNING], interim (2.5) |
| ev E0 - E3 | 10-24 10:50 - | the evaluation and the handover | [RUNNING], no artifact yet (2.5) |

Side branches: the reflex (stages 1 - 4, 10-23; branch reflex) and the no-landing query (airceil stages 1 - 3, 10-23;
branch airceil) - their findings fed S1 (the LEAD NOTES 3 and 4: the press validity, the side contact out of the air
sprint, the air dash restore) [P-m4].

### 2.5 In progress

THE ev WORKFLOW [RUNNING] (started 2026-10-24 10:50 PDT; [P-ev] has no stage entry yet): the person chose the lead's
option 1 after the tables did not speed the search live - E0 profile; E1 the fast evaluation (the escape funnel, the
danger per Clapper move / frame, the window shapes); E2 the handover (as logged: the drop rule, re-plan from
mid-action, the fallback mid-swing, the unpredicted hook reaction; the person's 10-24 ~10:40 decision also names the
plan as a tube - Q24); two verifiers; E3 fixes + a frozen checkout. Offline only.
T4 [RUNNING] (the stage planned on 10-23 19:55 after the verifiers; interim, from its commits and data): the merge key
with lane 0's extra air velocity and the held direction both lanes hold (key_l0, K_MOVEF), CB_JH (jump held without a
press) dropped only in a pass's first frame and written by the witness, the up slash whose thunk meets the ceiling
(CB_UP, upslash_band), a free attack holding back a queued dash (CB_FREE), the attack in the ground dash unmodelled
(press.unmodelled -> a forced collision in simulate), the executable family (OPT_EXEC / Cfg.exec_only), Cfg.h_pass,
Cfg.shapes, the flat layer's valid_until, Lib.kinds' steady states, the wall clip and the backward set's inexactness
documented (Back.exact); the acceptance at a deterministic budget re-run (off 95 / 112 / 72, found 207; on the same;
onlong 79 / 76 / 124, found 155; onshapes 96 / 108 / 75, found 204 [T4: a1n/t4/accept/acc_vc.txt]) and at 1 s / 0.25 s
(running); the funnel trial and eps(k) (2.1). Its relation to ev (who carries E1) is Q20.

---------------------------------------------------------------------------------------------------------------------

## 3. Architecture

### 3.0 Overview

L1 predicts every Clapper per frame under her planned path (closed loop: her hits and her position change its
choices), as outcome branches with probabilities and reveal frames. L2 says where she can be, frame by frame, from her
exact state (an envelope of x interval sets over a small family of vertical histories; the M1 engine today, the A1_n
tables as the exact memoised alternative). L3 finds strike / escape plans: candidates from the windows bound to the
enemy intersected with her envelope, each turned into concrete keys and checked in closed loop against every outcome
(the reveal rule), with an exit after it; the value ranks the safe ones. LIVE CONTROL runs the search in worker
processes, commits a plan only after an exact re-simulation from the observed state, executes it frame by frame
against the possible outcomes and hands back to the default planner (the fallback) on a drop. THE REFLEX covers only
the windows the search cannot reach in time after a reveal. THE LONG-TERM POSITIONING PLANNER [DESIGNED] supplies the
escape funnel, the escape / aim nodes and a score field that the strike planner adds to its strike value.

### 3.1 L1 - the enemy model (the Clapper) [ON]

THE SOURCE OF TRUTH = POLYGONS (boxes / circles / polygons of the game's colliders) per frame in the enemy's own frame
(origin its transform, facing +x, mirrored for facing), per timing variant (e.g. slam antic 47 / 48 / 49, Slam 0 4 /
5), each with a kind: DAMAGE / BODY / POGO (pogo-able) / TINK (bounces the nail; none on the Clapper) [spec, M2].

THE SIMULATOR (`clapper.Sim`, one Clapper per game frame; physics per step, then the FSM update) [M2]:
- physics: the lunge 30 u/s from the Slam 0 entry to the Slam 2 entry (~0.6 u / frame); the evade 15 u/s back (~21 f,
  ~5 u); the walk 8 u/s; the jump vx = Jump X, vy 38, gravity 84 u/s^2; the grounded transform follows the box bottom;
  the walls; the roof near the walls; her side slash pushes it 0.06 u per step x 8 = 0.48 u (also in the air; a hit in
  the air does not stop the flight).
- rules (the decompiled Control FSM, each checked on the recordings): TOOK DAMAGE only in Idle -> Dmg Attack in the hit
  frame (a walking Clapper has no Dmg Attack: Walk's own 0.25 s / Slam Range); SLAM RANGE = her physics box against the
  trigger +-8.046 u in x, -4.454 .. +3.369 u in y, with a 0.02 u contact offset, decided in the overlap's frame (the
  exit seen one frame late for Dmg Attack); Idle Time read at the Idle entry (1.15 s with a living buddy; the spec's
  'Idle 0.65 s -> Walk' - Q19); Walk >= 0.25 s with her in range -> Close Range; Will Evade 50 / 50 (drawn at the Idle
  entry) -> Evade at >= 0.25 s in range; Avoid Type at |dx| < 4; DistanceWalk by |dx| with the hysteresis 5.5 / 8.5
  (entry by 7); CLOSE RANGE: the buddy attacking -> CANCEL to Idle; the clip Walk B -> SLAM; after Evaded -> V4 SLAM /
  CAST; else V4 SLAM / EVADE / CAST (1/3 each); FAR RANGE: V4 JUMP 0.5 / CAST 0.25 / JUMP CAST 0.25; the V4 counters per
  action (eventMax / missedMax: no long repeats) replayed in `Memory`; THE ESCAPE: an evade with its wall < 6 u behind
  (the facing before the turn) -> the escape jump, JUMP / JUMP CAST alternating 1:1; EVERY MOVE'S START STATE TURNS TO
  HER (FaceObjectV2), Idle / Walk turn with the 0.5 s pause; JUMP AIM reads her x: target = her x - 5 x its facing,
  Jump X = clamp(target - its x, +-12) [M2]; the LANDING = take-off x + 0.916 x Jump X (0.916 s = the 55 f flight;
  forum.md 33 / 67: away from the walls 5.27 u in front of her x at its Jump Aim, p10 / p90 4.73 / 5.66 [SP3]); THE
  BUDDY LOCK: Close / Far Range read the other's Is Attacking (set from Slam / Spell / Jump / Cast Slam Antic to Slam 2
  / Cast 2) -> CANCEL; hp 0 -> dead, the body off from the death frame.
- THE JUMP'S WALL PUSH (the person, 2026-10-22, from the recordings; explained by M2): near a wall the roof polygons
  (Roof Collider_Basic (1) / (2)) meet the body's top at the end of the rise (take-off + 15 - 19 f) and the velocity
  slides along the slope (vx +-5 - 6 u/s away from the wall): the landing 1.3 - 3.6 u off the wall, the flight 43 - 46
  f instead of 55; the rise below ~14 u is unaffected - a ride up is unaffected, the landing x (and the jump cast's
  dome) must be predicted with the push.
- SHAPES: the body box per state and frame (the union over the frame and its neighbours); the hammer polygons on Slam 1
  (+ the first Slam 2 frame) and Slam 2 (+ the first Slam Recover frame; a jump's landing too); the slam's hammer is
  passed through, the Slam 0 body is the strike; the bombs: ring m at 0 / 10 / 19 / 29 / 39 / 49 f after the Cast 2
  entry +-1, lit 20 - 21 f later for 5 - 7 f (only those that reach the arena); the big rune: 6.75 / 6.48 u ahead by
  facing, y 3.342, r 7.187, lit at landing + 65 .. 72 (~3.45 u high over the landing point, ~7.5 u over its centre);
  a killed caster's hazards stay.
- BRANCHES: the random choices are drawn where they first matter (Will Evade where she is in range at Can Evade, the
  walk's far timer in 15-frame bins, the V4 picks, a planned hit in a move's last frames that may already be Idle);
  two Clappers are JOINT particles (the buddy lock couples them); each record carries its timing range [a, b].

THE API: `predict(enemy states, her planned path)` -> `Prediction.branches` (grouped by each Clapper's first 2 move
picks and its Will Evade draws): p, choices (kind, outcome, frame, reveal lo / hi), the reveal frame (when she can see
which branch it is), shapes(k), damage(k, margins), targets(k, POGO); `danger_boxes(k)` in her box centre's
configuration space with the margins. `Tracker` turns the observed STATEs into the observation (with the Memory and
the leftover hazards); `move_timeline(K, move)`; `Know.margin(move, k)` [M2]. Compiled (`clapper_jit`), identical in
10,689 predictions [M4b].

MARGINS (measured errors become growth): look-ahead margins per move and k for 99 % of the fit set's area - k <= 12
mostly 0 - 0.3 u, 36 f 0.2 - 1.0, 60 f 0.5 - 1.0, 90 / 120 f 1.0 [M2]; in-move margins for a move already under way,
by k since its start was seen - slam 12 f 0.2 u, 24 - 36 f 0.5, 60 f 0.75, 90 f 1.0; jump / jump cast <= 0.2 up to 60 f
[M3].

VALIDATION (fit 600 / held 424 / old 483 episodes) [M2]: V4 picks not allowed by the replayed counters 9 / 3 / 4 of
9,239 / 5,816 / 7,434; Close vs Far at Dmg Attack / After Scuttle 10,261 / 10,263, 6,006 / 6,006, 8,418 / 8,418; the
buddy lock 99.4 / 99.5 / 99.3 %; the escape ray >= 99.9 %; a move's start faces her 98.5 - 99.1 %; jump landing > 6
u off a wall p99 0.30 - 0.51 u, within 6 u p90 0.11 - 0.25 u; timing inside the realized branch's range 95 - 99 %
per state; true damage contacts covered at k 0 - 36 >= 96.4 %, at 120 f >= 94.8 %; area with the margins 98.7 - 100
% at k <= 60. Beyond ~36 f the misses are decision moments (her Slam Range entry, the buddy's
lock, an evade in the frame of her slash). Unexplained: 1.5 % of the move starts not facing her, ~7 % of Idle's turns
against the 0.5 s pause. Speed: one Clapper p99 5.0 ms, two 125 ms (Python), then compiled [M4b].

### 3.2 L2 - her reach

#### 3.2.1 Hero mechanics (measured; the HERO2 model)

HORIZONTAL
- normal ground / air control is instant: vx = 8.25 x direction, 0.165 u per step (0.164999935 in kin_jit's f32)
  [spec, T1].
- the ground sprint (after a ground dash): 28 -> 17.5 u/s at 1.1 per step, steady 17.5 u/s; released after Sprint
  Grace the skid (x0.85 per step, ~16 f), with the key held the run after it [M0].
- the float (UmbrellaMotionX, the previous frame's key per step): the umbrella antic's accel 8.5; the Inflate resets vx
  to 0 at its entry, then accel 1.0 / decel 0.25; Float Idle the same; a key released in the float drifts on ~3 u; the
  Umbrella Turn p50 19 f [M0, spec].
- the extra air velocity: after the air sprint's attack cancel x0.8 per step (10 / s), added only while no move key is
  held, gone at a turn / a landing / a regain [M4a]; after a sprint (shuttlecock) jump's cancel 18 u/s decaying 5 / s
  [T1].
- the unhooked Clawline's residual drift: vx 12.46 toward, x0.923 per step, skipped while a key is held, cancelled by a
  turn: +1.62 u with no key (0.81 / 2.17) [M0].

VERTICAL
- gravity 60 u/s^2 = 1.2 u/s per step; the max fall 30 u/s, reached after 0.5 s / 7.5 u from rest - possible in the
  ~12 u arena (the person, 2026-10-20) [spec]; kin_jit's terminal is -31.2 u/s after its clamp-then-gravity, the A1
  lattice A1_0 .. A1_25 (26 distinct vy) then A4 [T1] (Q18).
- the jump: hold 18.6 u/s; releasing jump while rising halves vy, also after the 9 rise steps (holding stays a live
  state while vy > 0) [spec, M1].
- the AIR HANG: holding jump through the apex sets the gravity scale to 0.1 at the first falling step, +0.1 per step
  while held, back to 1 on release [spec, kinematics].
- the float: the Inflate 12 f at vy +0.5, then -0.13 u/s per step toward -6 (M1: phases 0 .. 58); in the air show the
  float's vy p50 -1.3, its runs p50 10 f / p90 38 f [spec].

THE UMBRELLA
- the antic 5 - 6 f (5 once their time reaches 5 / 60 s: 313 / 326 opens) [M4a]; the earliest close 17 f after the
  open [spec]; THE DEFLATE: 6 f after the float (132 / 132), 7 when the jump was released inside the Inflate (26 / 27);
  it freezes vx (639 / 639 steps); then a plain fall at the float's vy [M0].
- THE RE-OPEN: a press before the umbrella FSM is Idle again (release + 11 .. 14 = the Deflate's 6 + its Cooldown 0.1
  s) does nothing (0 / 18); from release + 12 it opens at once (13 / 13) while she is >= 1.1 u up [M0].
- the attack: in Float Idle with jump held on the press frame (22 / 22, no Deflate); on the jump's release frame LOST
  (0 / 20); in the Deflate at once (19 / 19: its Attack Cancel); after it at once (34 / 34); in the Inflate lost at its
  frames 1 - 4 (6 / 6), at once from its 6th (9 / 9); in the umbrella's antic LOST (0 / 26) [M0].
- the Clawline: from Float Idle held or released that frame at once (43 / 43), from the Deflate / after it (16 / 16);
  LOST in the umbrella's antic (0 / 24); in the Inflate only when the key is still held as Float Idle starts (6 / 11)
  [M0].

THE ATTACK AND THE DOWN SLASH
- the next swing 18 f after the press at the earliest, after a whiff and after a pogo alike [M0]; the down slash active
  +3 .. +9 [spec]; presses go through InputHandler's 0.1 s attack queue [M4a].
- the down slash polygon (pogo_model DOWN / DOWN_ALT, alternating) spans ~3.2 u (1.25 - 1.5 u past the hurtbox each side
  at her feet's height, ~0.35 u past it 1 u lower; the lowest point ~1.17 u below her feet); her hurtbox 0.4554 x
  2.2498 u, centre 0.38 u below the transform [spec].
- a SIDE down slash (her box bottom below its body top, her box 0.03 - 1.7 u clear of its body in x) gives a full pogo
  bounce (41 / 42) [M0] - except out of the air dash / sprint (3.3.1, press validity).
- THE POGO BOUNCE: vy -10 on the contact frame, the slash's Bounce event at P + 7 restarts it: rise 3.74 u (79 % of
  115) / 4.09 u (16 %), apex contact + 21 / 22; a contact after P + 7 bounces once (~2.7 - 3.05 u); i-frames contact ..
  + 8 / 9 (DOWNSPIKE_INVULNERABILITY_STEPS 8) [M0].
- the game's downSpikeRecovery: after a POGO 9 - 11 f (1,292 airborne bounces; 15 - 23 f in 5 %); after a HOOKED
  Clawline's forced bounce 1 f (54 / 54); kin_jit's own lock DS_REC is 15 / 16 f (the press credit in 3.3.1) [S1b, AC3].
- a jump in the pogo bounce: pressed at P + 3 .. 6 (contact + 0 .. 3) lost (14 / 14); from P + 7 the umbrella in the
  press frame (31 / 31) [M4a].

THE DASH
- THE GROUND DASH: any number, the next one 25 f after the press (0.425 s; + 24 swings a frame late, earlier presses
  dropped, no queue), 7 - 9 f, 3.5 - 4.05 u [M0]; re-pressed around its end it sprints only with the key held on its
  last dashing frame [M4a]; a jump sets the dash cooldown to 0.05 s (a dash in the jump's first 3 f waits / is lost)
  [M4a]. The ground dash does not use the air dash: after a ground dash and a jump the air dash fires (27 / 27) [M4a].
- THE SPRINT (SHUTTLECOCK) JUMP: jump in a ground dash held into the sprint / in the sprint -> the Jump Antic for
  0.1083 s (the jump in the antic's 7th Update), her x speed kept, then 18 u/s along her facing while rising, jumped
  steps -5, the dash cooldown 0.1 s; ends on the ground or at an attack / a Clawline (ShuttleCockCancel: the extra air
  velocity 18, decay 5 / s) [T1: H2_SHUTTLE, 50 / 52 trials]. The sprint's DASH ATTACK (the Wanderer lunge) is NOT
  modelled (3 trials) [T1]; an attack pressed in the ground dash or sprint (the lunge, 2.6 - 3.9 u off the model in
  M4a) is now flagged unmodelled: the envelope never offers it, its reference drops it, a plan with one is not played
  (`press.unmodelled`, a forced collision in simulate) [T4].
- THE AIR DASH: from P two 28 u/s steps (vy reset to 0 each step, then gravity 1 - or 0.1 with jump held - in the
  step), the Air Sprint from P + 3 / 4 for 14 f (no control; 26.9 u/s, falling 1.1 per step under an easing clamp -10 ->
  -30 u/s over 1 s; extended at 12 u/s while the dash is held), control at P + 17 / 18; dx at P + 10 4.02 - 4.42 u, at P
  + 15 5.17 - 5.83 u [M1, M4a]. With jump held ~0.3 u higher at the sprint's end [M1, M4a]. Because the dash zeroes
  vy every step and gravity then acts in the step, the sprint's vy runs like the fall from rest [spec, M4a]; whether
  the easing clamp bites at the end of a long sprint (the end then off the A1 lattice) is unchecked (Q26).
  - its ATTACK cancel at max(AS + 4, press + 1) (AS + 3 after a 2-step entry frame), the press read through the attack
    queue (kept from up to 3 f before AS, lost from 4 f before), then the extra air velocity [M4a]; an attack queued
    into the sprint's last frame swings (H2_SPR_FIN) [S1b].
  - its JUMP cancel on the press frame: the umbrella at once when it can open, else (near the floor) the loop and a
    regain the next frame; a press on the dash's last frame acts at AS [M4a].
  - the Clawline at once from any air sprint frame (29 / 29); in the dash's two steps it waits for their end [M4a];
    the engine offers it so since S1 (HERO2 H2_CLAW_SPR, `env_jit.claw_allowed`) [S1, code].
  - one air dash per airborne stretch; RESTORED by a pogo (28 / 28; at contact + 9 .. 14 after a dash - its 0.425 s
    cooldown -, + 3 / 4 otherwise) [M0], a hooked Clawline (27 / 27, at control) [M4a], a landing (BackOnGround;
    H2_LAND_DASH; no trial covers dash -> land -> dash) [T2]; NOT by the unhooked Clawline (23 / 24) or the umbrella
    [M4a].

THE CLAWLINE
- the needle hits at P + 8 / 9; no i-frames in the Clawline [M0, spec].
- UNHOOKED: the antic from P, the throw at P + 9 (air 51 / 60, P + 8 in 9; ground 7 / 8), the throw 10 f still, the dash
  70 u/s for 0.1 s (6 steps, 8.4 u; 172 / 173), the Catch 6 f (x0.75 per step), control at P + 32 (30 .. 33); the pull
  P -> control 10.6 u (p10 9.4 / p90 10.8; ground 9.2 - 10.6), the height held; it ends with vy 0 and no bounce (an A1
  start) plus the residual drift; the antic's drift = her vx x 0.975 per step [M0, AC1]. A second Clawline: lost before
  control + 13, at once from + 13 (the Harpoon FSM's Wait 0.2 s) = THE CLAWLINE LOCK; the attack and the dash are free at
  control. 13 f < the ~30 f block: no 'Clawline ready' key - an online lock [M0].
- THE HOLD HEIGHT: the Harpoon Antic clamps vy to [-10, 5] and multiplies it by 0.875 on entry and per step (gravity
  off) to the throw: held bb = bb + (0.0744 .. 0.0804) x clamp(vy, -10, 5) with the free-flight vy at the latched frame
  (residual p10 / p90 0.000 u); from the ground 0.25 u [M0].
- THE RAY: 9.75 u from her centre at the needle's hit (P + 8) to the body's near edge; the band = her held bb + 0.5 ..
  + 1.98 u (SP13 claw_cal). The model's reach to a standing Idle facing her 11.99 u (facing away 11.08; +-0.98 u for her
  vx +-8 u/s); a standing Idle is hookable from bb 0 .. 3.40 u (vy 0; up to 4.15 u falling fast). Live-probed only to
  10.2 u to the front (hooked presses 3.1 - 8.6 u) [AC1, AC2a].
- HOOKED: the dash stops ~2 u before the body [spec]; control at P + 23 at the earliest (the search's reaction key)
  [M3] (Q16: the spec's SP13-convention timings); the forced bounce 4.09 u over the control frame's box, apex control
  + 22 / 23 (19 / 19) [M0]; the attack waits to control + 10 / 11; a second Clawline from control + 12 / 13, and it cuts the forced bounce (vy clamped to 5,
  x0.875) [M0]; the air dash restored; the hooked body is harmless from P + 17 to control + 12 and hurts from control
  + 13 at the earliest, + 14 usually (the Harpoon FSM's Idle + 1) [M4a]; the hooked one's reaction is the Idle
  reaction above (a hit on an Idle Clapper) [M0].
- the direction: the game throws toward her FACING; a press latches as a rising edge, so the direction key must be
  latched at P (or she already faces the target) [M4d].
- the Clawline from the ground is allowed by the game (M0's 34 claw_gnd trials) but not offered by the envelope (T1
  open item 4).

OTHER
- SILK IS NOT A STATE (the person, memory silk-not-a-constraint: a hitless bot never binds, the Silk Heart
  regenerates; silk full on 85 % of a two-Clapper run's ticks [OLD]).
- the end of a hit recoil: v 0 after 0.2 s (an A1 start) [spec].
- WALLS: the hero model kin_jit has the wall slide, the cling and the wall jump (rows WSIDE / WTOUCH / CLING, WJ_*;
  the Forum loadout's ability bits) [code: kinematics.py]; the envelope engine and the tables have no walls (M1: a flat
  floor); the search treats the walls as closed danger boxes at her half width, so she never touches one; the
  use-time x clip (`Lib.forward(wall=)`, 3.2.2 TERRAIN) misses the walls' vertical effects (the slide, the cling) and
  is not used by the search [T4] (6.2).

#### 3.2.2 The envelope principles (the person's design, 2026-10-20 .. 23)

- ONE FOR HORNET, EVERY ENEMY (the person, 2026-10-20 evening): the envelope is fight-independent and precomputed
  before the fight per hero kit (crest, tools, abilities), with her current position as the origin - independent of
  her map x / y (translation invariance: x never enters a key) - and keyed by her movement state; terrain and danger
  are applied at use time. As built: a library refuses another hero model's params sha1 (3.2.4 LIBRARIES).
- NO KEY ENUMERATION (the person, 2026-10-20 [OLD]): because the normal control's horizontal is instant, the reachable
  x after n frames is exactly the interval between 'all left' and 'all right' - not 3^n key strings. The float has
  inertia: its x reach is bounded by two LANES (always-left / always-right) and, planned ahead, every x between the
  lanes is reached closely enough - the float's horizontal is an envelope too, its growth following the lanes
  (the person, 2026-10-23). Horizontal and vertical stay decoupled (the instant run, the jump hold / fall / umbrella act
  on y only).
- THE AIR = HORIZONTAL INTERVALS x DISCRETE VERTICAL CURVES (the person, 2026-10-20): the fall is one-way and only a
  few EVENTS change vy, each to a fixed value with its own lock - the jump press / hold / release, the air dash, the
  umbrella open / close, the Clawline, a pogo / a hooked Clawline's bounce, the air hang. Otherwise free fall. So the
  vertical state is a small discrete family of curves y(k), vy(k) glued at event frames.
- AN EVENT = a discrete key change that changes the vertical or the mode (a jump press / hold / release, a dash, the
  umbrella open / close, the Clawline, their cancels) - not left / right (free every frame, inside the widening) and
  not an attack in normal control (the person, 2026-10-24).
- DANGER CUTS X ONLY (the person, 2026-10-20): danger never changes her vy, it removes x (and kills a piece whose x is
  all gone); vertical pieces are created only by events, few per airtime because of the locks.
- PROPAGATE STATES AND MERGE, NO ENUMERATION OF EVENT ORDERS (the person, 2026-10-20): a frame-by-frame forward pass
  over states; each frame every state continues (x widens by its mode's reach) or starts an allowed event; states
  with equal keys MERGE (their x sets unite), so different event orders that end in the same state cost nothing;
  dominated states (same key, a subset x) are dropped; every frame is a possible event start.
- THE CLUSTER (the person, 2026-10-21 / 22): one vertical trajectory = (its TYPE - the curve and its phase -, its
  SPACE-TIME ORIGIN, the flags / locks) with an x interval set per frame; its free evolution is its type's table
  translated to its origin. An event maps 'prior state at the event frame -> (type, origin)' exactly: the TYPE is often
  history-free (the air dash -> an A1 state at its end - on the lattice unless the sprint's eased fall clamp bites,
  Q26; pogo -> the 3.74 u bounce; hooked control -> the 4.09 u bounce; open -> A3 after the Inflate; landing ->
  ground walk) but the ORIGIN is not always (the umbrella antic falls 6 f from the prior vy; the
  Clawline's hold height depends on vy at the press; the close continues the float's vy - A1 joined at the phase with
  that vy - and freezes vx for 6 f; the unhooked Clawline ends at A1 with the residual vx).
- STEADY / CANONICAL STATES (the person, 2026-10-20 / 23): a continuation (a table, a waypoint, a junction) starts only
  from a state fully given by its position plus a few flags - standing on the ground (walk) or running (the sprint),
  an apex / at rest (A1), the float (A3), the terminal fall (A4) (later: the wall cling). Transitional states (a jump's
  2nd .. 20th frame, a bounce's rise, the umbrella's opening, a dash in progress) live INSIDE a segment that starts at
  a steady state. STEADY = every hidden state that affects later actions equals the target's origin: the timers that
  can be waited out are waited out (the 0.1 s attack queue; the extra air velocity; the Clawline lock to control +
  13; the umbrella re-open lock; the downspike recovery; the dash cooldown; the jump buffer; i-frames) (the lead,
  2026-10-23, the person agreed).
- THE CANONICAL STATES (the person, 2026-10-20 / 21; final details from M0 / M1 / T1): A1 = at rest / falling on the
  fall-from-rest curve (its phase IS its vy; an apex, the end of a hit recoil - v 0 after 0.2 s -, the unhooked
  Clawline's end; flag: the air hang available - only after a jump held through the apex, not after a bounce); A2 = a
  bounce's rise from its first controllable frame (vy +17.4 in the 5-frame constant phase; two variants: the pogo 3.74
  u, the hooked Clawline 4.09 u; flags: the i-frames, the attack ready ~18 f after the press / control + 10); A3 = the
  float from its first steady frame (the Inflate's end, vy +0.5, then the curve toward -6 - a curve, not a constant: it
  reaches -6 only ~1 s after the Inflate and most floats end before); A4 = the terminal fall (the only constant vy);
  G = standing / walking; R = the ground sprint past Sprint Grace. TABLES CHAIN AT THEM: A2's do-nothing branch IS A1 at
  the apex, an umbrella opened in the rise hands over to A3, A1's plain fall reaches A4; the close is a Deflate
  carve-out after which she JOINS A1 at the phase with the same vy (tables are indexed by phase, not only entered at
  frame 0; a joined cluster is empty before the join - a virtual origin). Every table is short; long reach = tables
  chained at canonical states, time-shifted and translated (R(s, t1 + t2) from R(s, t1)'s canonical ends and R(s',
  t2)). END CONDITIONS of a table: the strike windows (can slash / can down slash / can Clawline) and the steady states
  without the apex (ground, float); the APEX is never an end condition - after a strike the STRIKE MODULE produces the
  next steady state (3.3.7). As built in M1: all / can slash / can down slash / can Clawline / on the ground / floating.
- NOT TABLE KEYS (the person, 2026-10-21): what does not change where she can be - the attack cooldown (a time mask on
  the 'can slash' flag) and the pogo i-frames (no cuts while they run) - is handled online; a short lock (the umbrella's
  re-open, the Clawline's 13 f) may be over-approximated in a free-space table and enforced exactly online and in the
  final re-verification.
- THE COUNT SATURATES (the person, 2026-10-21): at a given frame a cluster is (the curve, its phase, the height, the
  flags), bounded by the arena and the curves, so the per-frame count does not grow with time without bound; clusters
  also die (cut, landing), hand over, merge and are dropped when dominated, and the backward pass from the goal windows
  keeps only those that can still reach one. Staying up 120 f at all needs the float or bounces (an unbraked fall from
  12 u lands in ~38 f). Measured: M1's counts (3.2.3). With one event the per-frame states grow only linearly and
  saturate (the person, 2026-10-24; a statement, not measured by a stage).
- THE (x, y) PROJECTION IS FOR QUERIES ONLY (the person, 2026-10-20): 'where can she be at frame T', the danger / terrain
  checks and the display use the flattened region; the computation keeps the curves and phases; vy is an attribute of a
  point, used when continuing from it or timing a strike. An air dash splits the x set into lobes with a hole - interval
  SETS hold it.
- ZERO-TIME RELABELS ARE ALIASES (A2 at its apex IS A1 phase 0; A1 at the terminal IS A4), one canonical name each, no
  self-loops; THE RECURSION IS CAUSAL: every event takes >= 1 step, so the state graph's cycles (A1 -dash-> A1, A1
  -open-> A3 -close-> A1, A2 -> A1) unroll in time into a DAG: compute by increasing t (the person, 2026-10-21).
- TIME IN PHYSICS STEPS inside the tables (some 60 fps frames have no step, so 'n frames of fall' does not fix vy);
  convert at the interface (the person, 2026-10-21; the lead's point 3, 2026-10-23).
- TERRAIN AT USE TIME (the person, 2026-10-20): the tables are terrain-free (in the air infinite height); floor, walls,
  ceiling and danger are applied at use time. Terrain contacts are BRANCH EVENTS, not end states: where the
  envelope's lower boundary first touches a floor / platform top, those positions at that frame become a ground start
  at that floor's height (a landing height need not equal the take-off height); walls (cling / slide) and ceilings (a
  bonk resets vy) are contact events of the same kind. Walls are absolute: clip to the arena after every widening step,
  then go on widening (she can run along the wall or back) (the person, 2026-10-23). As built the clip is x only and
  misses the walls' vertical effects; the search uses closed wall boxes instead (3.2.1 WALLS) [T4].
- INVINCIBLE SEGMENTS KEEP THEIR POSITIONS: the Clapper chooses from her position even while she is invincible, and the
  terrain changes the endpoint - positions are kept, labelled 'cannot be hit, cannot attack' (the lead, 2026-10-23).
- THE GROUND TABLE (the person, 2026-10-21): on the ground the take-off time and place are free, so a ground table is
  the union over the take-off time of the jump tables dilated by the walk interval reached by then (a Minkowski sum),
  plus the stay-on-the-ground part - one deterministic table per ground start (walk, run). Because left / right is
  decoupled and the air speed equals the walk speed, it is close to 'x in [-X(t), X(t)] x y in [0, the running max of
  the jump height]', with corners where the sprint / dash couple; it holds only the union - the per-take-off arcs for
  the danger cuts are rebuilt online. The ground tables hold walk / run, the GROUND DASH (unlimited, >= 25 f apart),
  the ground sprint it leads into, the jumps out of it (the sprint jump; built, T1b) and the sprint's dash attack
  ([DESIGNED], not built: not modelled, T1b; flagged unmodelled, T4) (the person, 2026-10-23 evening - Q27 on the time:
  'the ground should do the dash; after a ground sprint jump she can still air-dash'). Leaving the ground starts an
  air segment with its one air-dash bridge available.
- THE AIR DASH IS NOT IN THE TABLES (the person, 2026-10-23): every table is a no-dash table; the dash family is an
  independent module, THE DASH BUNDLE, used only as the BRIDGE between a forward and a backward no-dash set (3.2.4).
  'Air dash used' is not a table key but a property of the segment between two refills (a landing, a pogo, a hooked
  Clawline); the tables carry per frame only whether an air-dash PRESS is allowed (airborne, the dash unused, no lock
  such as the umbrella's antic).
- THE UNHOOKED CLAWLINE IS AN EDGE, NOT A KEY (the person, 2026-10-21): fight-independent mobility from every air state
  where it is allowed, left or right, ending in an existing state (A1 with the residual drift); no 'Clawline used' key;
  its 13 f lock is an online lock. It is slower than the dash for short hops, faster for long ones (70 u/s) (the
  person, 2026-10-20). The HOOKED Clawline is target-dependent: added at use time by the strike module (a hook on an
  Idle Clapper is a hit and triggers its reaction).
- DISCRETE ALTERNATIVES ARE BRANCHED, NOT WIDENED (the person, 2026-10-24): e.g. the pogo recovery 9 - 11 vs 15 - 23 f
  (5 %) [S1b], the bounce 3.74 vs 4.09 u - a width covering them would be too wide and kill good plans.
- NO SNAPPING (the person, 2026-10-21, final): the precomputed tables are exact, and online the pass starts from her ONE
  exact observed state, so every derived cluster is exact; nothing is snapped to a lattice, anywhere.

#### 3.2.3 The M1 engine (as built; the live envelope) [ON]

`brain/ssbot/map2/env_jit.py`, `envelope.py` [M1, M4a]: a CLUSTER = one vertical trajectory held as a full kin_jit
state (height, vy, gravity scale, mode / phase, the timers and flags) + an x interval set per frame; clusters merge
only on a bit-equal canonical vertical key (spent timers / queues canonicalised). The recursive element is kin_jit's
frame: each frame a cluster rolls its physics steps once, then branches on every choice that changes its vertical
state or mode (jump pressed / held / released, dash pressed L / R or held, the attack's cancels of the umbrella and the
sprint, the unhooked Clawline L / R with its P + 8 / P + 9 throw); every child comes from its parent one frame earlier.
Two LANES per cluster (always left / always right) bound every member's x displacement ([a, b] -> [a + dlo, b + dhi]);
the extra velocity widens the lane on its side (`xvx_extra`, the key slot K_XVD). Danger = boxes in her centre's space,
cut per child at its own height every frame. THE EVENT LIMIT (the spec's segment family): events = presses, releases of
a key whose hold still acts, the Clawline; inside a segment every frame is exact. WITNESS: back along the cluster chain
(the vertical choices + a tube of x), then left / right by a greedy tracker or a beam search (24 states), re-simulated
by the reference model. The engine does not offer: the ground Clawline (T1 open item 4), an attack in the ground dash /
sprint (the dash attack, T1b; `press.unmodelled`, T4). The Clawline from the air sprint IS offered since S1 (HERO2
H2_CLAW_SPR in `env_jit.claw_allowed`: M4a open item 2 closed), except in the dash's two steps [S1, code].
NUMBERS [M1, M4a]: 0 escapes (exact 12 f 120 x 300; <= 2 events 30 f 400 x 300 on the floor; the same + 4 moving danger
boxes); witnesses 1,600 / 1,600, 98.5 % within 0.1 u; pass time (100 starts, one thread) <= 1 event 30 f 4.5 / 17 ms,
60 f 14 / 44 ms (12.5 ms after M4a); <= 2 events 30 f 67 / 208 ms (47 ms); the threaded `forward_par` bit-identical,
the heavy 2-event passes 410 -> ~165 ms on 4 threads [M4b]. CLUSTER COUNTS: A1, free space, no limit 23,831 at 16 f
(286 without the air dash; 62 without the Clawline and the dash) - the air dash's family (every start frame x direction
x jump held x cancel frame) is the bulk.

#### 3.2.4 The A1_n recursive tables (the person's design, 2026-10-23; built T1 - T3; T4's fixes running) [OFF]

THE DESIGN (the person, 2026-10-23 morning; agreed with the lead's points; built after the gate on the person's
decision of 2026-10-23 ~19:50 'build the recursive tables directly'):
- A1_n = the free-fall table whose space-time origin has the vertical velocity of n steps of falling from rest
  (A1_0 at rest, A1_1 one step of fall, ...); x, y, t relative to the origin.
- NO REDUNDANCY: A1_n = A1_n+1 referenced one step later (moved by that step's fall, its left / right reach widened by
  one step) + ONLY what the actions pressed at its frame 0 add. An action pressed at frame 10 (the spec's example was
  the dash, which is now the bridge) sits in A1_10, reached through the chain A1_0 -> ... -> A1_10. Exact because the
  normal fall's run is instant and memory-free. A pressed action keeps its space-time trajectory (an x interval per
  step) inside its table until it reaches a steady state, labelled per step LOCKED (can be hit, cannot attack) / TRANSITIONAL (can be hit, can attack) / INVINCIBLE (cannot be
  hit, cannot attack); at the steady state the table stores the endpoint, the REFERENCE (which table continues there)
  and the action id.
- A REFERENCE CARRIES THE WIDENING (the person, 2026-10-23): a reference = (target table, dt, dy, an x OFFSET INTERVAL
  [lo, hi]); references compose by adding intervals; a trajectory seen through [a, b] becomes [x_lo + a, x_hi + b].
  The WIDEN method per state: A1 +-0.165 u per step each side (exact); the float by its lanes (stored per frame); the
  extra velocity stays inside the transient's trajectory until spent. After a danger cut each piece is widened and
  merged - exact for the instant run and the committed blocks, an over-approximation inside the float's inertia after
  a cut [M1] (4 EXACTNESS).
- THE FLOAT'S HORIZONTAL IS AN ENVELOPE (the person, 2026-10-23): the reference into a float carries an x interval AND
  a vx interval (the low lane from (x_lo, vx_lo) holding left, the high lane from (x_hi, vx_hi) holding right); one
  float table per vertical phase (~59); the lanes saturate after a few held steps, after which every branch widens by a
  constant. Build-time checks: monotonicity incl. the Umbrella Turn; the gaps between the discrete in-between x well
  under a window's width; the witness for keys / vx.
- ENTRY FROM ANY STATE (the person, 2026-10-23 evening: 'a transitional state has no table of its own - the gate's bug
  (a plan dropped mid down slash) would get worse'): steady -> its table; transitional (mid dash / sprint, mid down
  slash, the umbrella's antic / inflate / deflate, the Clawline's pull, a bounce's lock) -> roll the rest of the
  transient online with the exact model over its remaining choices until every branch is steady, then chain the
  tables. The search must be able to re-plan from mid-action. An index from a transitional state to 'action a of table
  T at step k' is an optimisation for later [DESIGNED, not built; no stage took it].
- MEET IN THE MIDDLE (the person, 2026-10-20 evening): a goal at a later time (a window's press region at frame 20)
  has a BACKWARD envelope - the states from which it is reachable in n frames; forward from her (danger subtracted)
  meeting backward from the goal (danger subtracted) at a STEADY junction state is a path around the obstacle. The
  junction is picked inside the overlap where the margin is largest, and the keys come from both halves' witness
  paths. The horizontal is time-symmetric (the instant run) but the vertical is not (gravity), so the backward tables
  are precomputed separately, keyed by the arrival state (steady goal states or window events). Per frame forward x
  backward is the tube of all feasible paths: the robust choice and the commitment monitor. The search asks per window
  'forward x backward non-empty?' instead of branching at every touch. Status: M1 built backward tables as the point
  reflection of its canonical tables (`Tables.backward / meet`) [OFFLINE, unused - M1's canonical tables need a
  rebuild, M4a open item 4]; T2 built the backward set over the chain (`bridge.backward`, AS BUILT below) [OFFLINE, not
  wired]; the search instead meets a window by its forward rows x the window region (the press points) and takes the
  keys from the chain's back-pointers - 'what a backward set would give it' (T3); the junction-by-margin rule is not
  built.
- THE DASH BUNDLE AS THE BRIDGE (the person, 2026-10-23): between two refills a path is no-dash -> (at most one air
  dash) -> no-dash. Push the no-dash sets FORWARD from her state and BACKWARD from the goal (the next strike window's
  press region, or a safe endpoint); join them with a dash variant d (dx_d an interval, dy_d, T_d, end state e_d) where
  F(t1) shifted by d meets B_e_d(t1 + T_d); without a dash F(t) meets B(t). The dash ignores her vy at the press, so
  the forward side needs only where / when a press is allowed; the dash's own tube (~17 f) is cut by the danger too.
  Its cost: interval shifts and intersections over ~120 start frames x the bundle's variants grouped by (dy, T, end
  state), instead of a forward set multiplied by every dash (M1's 23,831 clusters). The backward side is needed only
  INTO the dash's end tables: each variant ends in one fixed table whatever it started from (A1 lattice tables - the
  sprint's end, the attack cancel after its extra velocity; the lattice after a long sprint is unchecked, Q26 -, the
  float's first frame - the jump cancel, vx as an interval -, A1_0 after an unhooked Clawline), so B(window shape, end
  table) can be precomputed offline per pair and the bridge check becomes a lookup (the person, 2026-10-24) [DESIGNED]
  (Q6). As built (T2 / T3) the bridge is the chain itself: `Lib.forward(dash=True)` below.
- FLATTENED AND CHAINED, BOTH (the person, 2026-10-23): a FLATTENED union per start state and frame (where she can be,
  not how; danger-free, so an UPPER BOUND: prune windows outside it; exact until the danger first touches it) AND the
  CHAINED tables (from the first touch on, step frame by frame and cut each frame's danger). Keys are reconstructed only
  along the chain; back-pointers live on clusters, never on a flattened map (3.2.5). Precomputed sets (the backward
  sets, B(window shape, end table)) keep their own chain's back-pointers; the position-flattened maps stay
  pointer-free, an upper bound for the prune (the person's analysis, 2026-10-24, 90b62e8). As built the flattened layer
  is an upper bound only up to `Tables.valid_until`: for a start whose physics phase gives the build's step pattern,
  and for an air table only until its rows come within CLEAR 2.5 u of the floor / CLEAR_UP 1.0 u of the ceiling [T4].
- THE COLLAPSE IS FREE (the person, 2026-10-21): every decision her exact state picks its start node, translated to
  her exact x / y; old clusters are never 'collapsed', they are rebuilt from the exact state with the cuts.
- USE (the person, 2026-10-23): the search looks the tables up instead of rolling the physics per frame online; a
  bounding box per action (its trajectory + its endpoint table's reach) prunes the lookups [DESIGNED, not built]; the
  same pattern for A2, A3 and the ground.
- LONG HORIZON = FEW EVENTS, MANY EVENTS = SHORT HORIZON (the person, 2026-10-24): the ~2 s look-ahead is needed only
  for TRAPS (the safe region closing from afar, e.g. a far Clapper's jump cast) and escaping is running (0 - 1 event);
  so the long checks (the exits, the traps; 120 - 180 f) run with <= 1 event, several events only in short
  goal-directed chains toward a strike window (the hook -> umbrella -> down slash class, < ~1 s), backward from the
  window and bridged. No '3+ events x 120 f' passes. No coarse far layer (the person, 2026-10-24): with <= 1 event
  the long checks stay exact and cheap at the tables' resolution, coarse cells would close real narrow ways, and the
  far uncertainty is the funnel's eps(k) (3.3.4).

AS BUILT [T1, T2, T3]:
- THE NODE (the recursive element): one cluster state of the M1 engine made relative (both lanes' full kin_jit states,
  x relative to each lane's own x, y relative - or absolute over the terrain as a FLOOR / CEILING INSTANCE within
  CLEAR 2.5 u under her box bottom / CLEAR_UP 1.0 u over her box top); identity = the engine's merge key without the
  heights and the air-dash bit + each lane's horizontal state + the time scale. EDGES per node, per frame step count s
  in {0, 1} (the physics phase is a global clock: nodes are phase-free, edges depend on s - the spec's 'time in physics
  steps'), per pass kind (free / over the terrain), per event list (every choice / the event limit reached) and per
  dash status (du 0 no-dash with the dash unused, du 1 every candidate with the dash unused - the bridge's entries
  marked -, du 2 the dash used incl. the dash's own frames, du 3 no-dash with it used): (child node, candidate, x offset
  interval [dlo, dhi] + a phase slope where the drawn position moves her, dy, events spent). A1_n's going-on edge with s
  = 1 widens by exactly +-0.164999935 u, with s = 0 maps to itself.
- THE CHAIN (`Lib.forward`): per frame each cluster (node, heights, x set, events) maps through its node's edges;
  children merge on the engine's key exactly as the engine does; danger cuts each child at its height; entry from any
  state = the start node expanded on the fly with the engine's kernel until library nodes. `Lib.forward(dash=True)` =
  the no-dash chain + the bundle entered at every frame where a press is allowed + the post-dash chain.
- THE BUNDLE (`bridge.bundle`): the ends' (dt, dy, x offsets) are the same for every A1_n of one physics-step pattern
  (31 / 31 in each of the 6 patterns - the person's 'one shared bundle' holds; the end NODES too but one of ~4,900,
  which carries the press frame's vy); 5 entries (press L / R, with jump held
  L / R, the queue); the search's library 4,689 - 5,121 end groups, with the Clawline 19.8k - 30.2k. THE BACKWARD SET
  (`bridge.backward`, numba): a goal region pulled back over a pass's pieces (the danger / wall cuts the pieces' own),
  0.03 - 0.9 ms per window (<= 1 event 60 f) / 0.2 - 12 ms (<= 2 events 30 f) [T2]; exact for the instant run and the
  committed blocks, an UPPER BOUND inside the float's inertia (the verifiers' example: the end members miss the goal
  by 1.66 u) - `Back.exact` says which, and a use that needs the exact set (the funnel's 'inside') must confirm an
  inexact one forward [T4]. B(window, end table) NOT precomputed (T2 open item 3).
- THE TABLE VIEW (`Lib.table`, `Lib.kinds`): kinds A1 (lattice), A1~ (an offset chain, e.g. jump held), A4, A2, A3, G,
  R, hang, transient; per action the per-step offsets / labels / press flags, the end reference. The jump-held dash
  variants are their own nodes off the lattice (the lead's point 2). The action count: the recursion IS the 'sprinting
  at step m as its own chain' alternative (the lead's point 5) - A1_n's frame-0 actions without the air dash are 5 (the
  umbrella, the Clawline L / R and its P + 8 throw L / R).
- THE BUILD-TIME CHECKS [T1]: the A1 chain on kin_jit's own lattice (26 distinct vy, then A4); the going-on edge widens
  by exactly +-0.164999935 u per step; the float's monotonicity incl. the Umbrella Turn (20,000 random key sequences x
  40 steps over a vx grid of 35, 4,000 reversals): 0 order violations, 0 members outside the lanes; its gaps <= 0.025 u;
  the float's entry vx bit-equal over all 3^11 antic key patterns (1 distinct value; the lanes +-8.5 u/s). Kinds in
  T1's default library (2,264,311 nodes): transient 2,018,489, A1 10,289, A1~ 103,494, A4 2,254, A2 6,884, A3 85,503,
  G 1,022, R 3,598, hang 32,778.
- THE FLATTENED LAYER: 330 tables (31 A1_n + A4 + A2 x 2 + A3 x 18 + G x 3, x 6 phase classes; <= 1 event, 120 f), 53
  MB, 86 MB with the dash; rows = the chain's raster bit for bit [T1, T2] (its upper-bound limit: FLATTENED above).
- LIBRARIES (generated, git-ignored; the tracked header knowledge/1.0.30000/kinematics/a1n_tables_v1.json; a library
  refuses another hero model's params sha1 and, since T4, an older engine revision): T1 the default (Clawline in, the
  floor) 2,264,311 nodes / 7.8M edges, 194.1 MB, load 7.0 s, the search's (no Clawline, floor + ceiling) 721,029 /
  71.5 MB; T2's rebuild 2,404,844 / 8.4M, 223 MB, build 49 s + save 32 s, load 9.3 s, the search's 815,147 / 2.5M, 84
  MB, load 3.2 s (T3 used T2's); T4 rebuilt both at 12:30 (engine revision t4d; the header not committed): the default
  1,833,868 nodes / 3,450,600 edges / 161 MB, the search's 537,020 / 988,633 / 55 MB [T4, interim].
- IN THE SEARCH (`search.Cfg.tables` / `LiveCfg.tables`, default off): `World.envelope` is the search's one pass
  function - the approach passes and the exit checks; on: `tables.Lib.forward(..., dash=True)` returning the engine's
  `Fwd`; the engine when the library is busy on the other thread or her state has no table; the library loaded once per
  process (3 s) with a growth budget (400,000 nodes, then `Lib.reset` to its loaded state, exact, 35 ms); the long
  pass `(events, frames, t_from)` e.g. (1, 120, 60). Not wired: the backward sets (the forward rows x the window region
  give the same press points; the chain's back-pointers give the keys) and the flattened prune (only for the canonical
  starts; the danger touches her flattened union within 0 - 25 f, p50 8, in all 673 exit checks) [T3]. T3 found the
  long pass changing little (200 units: 2 better / 0 worse, nothing new found; the smokes' share 21.3 / 19.1 %) - all
  measured before T4's `Cfg.h_pass` fix (the predictions ended at the plan's end + 74, so the long pass's frames after
  ~75 saw no Clapper danger); T4's interim re-run at the deterministic budget: onlong found 155 vs off 207 [T4:
  a1n/t4/accept/acc_vc.txt]; the reading is open until T4 reports.
WHAT DID NOT HOLD [T1, T3]: the closure over 'a couple of hundred start states' (the person, 2026-10-21) does NOT
converge - the library is the memoised engine. A live decision meets 10 - 200 k NEW exact nodes; 15 s of a recorded
w7 episode grew it by 1.0 M nodes (~4.6 GB): 59 % floor instances by exact height, 41 % free states off the lattice;
exact states recur within a decision, not across decisions. A new node costs 8.8 - 11.7 us vs the engine's 1.6 us per
cluster-frame, so short live searches run cold: the first safe plan ~20 ms later, map2's share lower. Warm the tables are
4 - 6x faster; a 1 s search evaluates ~40 % more candidates. Only the 1-event family affords 120 f in a live decision
((1, 120): engine 20 ms, warm 3 ms); 2 events over 60+ f cost 0.2 - 0.8 s, 3 events 2 - 26 s. Memory: 3.3 GB resident
per search process + growth, 5 - 20 GB. Recommendation (T3): keep the switch off live. The fix (states that recur: a
floor instance only where a frame reads the terrain at that height - a per-node clearance -, and / or one library
shared between the workers, memory-mapped) is deferred by the person (2026-10-24) (Q5).

#### 3.2.5 How to get there - paths and keys (the person, 2026-10-22)

- BACK-POINTERS LIVE ON FULL STATES, NEVER ON THE FLATTENED MAP (the person found the flaw, 2026-10-22): a projected cell
  can be reached in very different full states; with one pointer per cell C may point to B while B points to A', from
  whose state C cannot be reached. A cluster is one vertical history, so its parent and its event frame are unique.
- A PATH = THE EVENT LIST: the non-left / right key events (jump press / release, dash, umbrella open / close, Clawline,
  attacks) with their time and place; left / right between them is rebuilt. Reconstruction: the clusters whose height
  at t is the target's y and whose x set holds its x, walked back for the vertical events; inside each cluster x is
  rebuilt backward (the instant run: clamp into the previous interval - it exists by construction of the dilation;
  inside the float a bang-bang path between the lanes).
- 'EXACT COMPUTATION' = simulate THAT concrete key string with the exact hero model (HERO2) and check it frame by
  frame against the predicted danger (with its margins) before committing - the tables say what is possible, the
  simulation confirms the chosen path.
- As built: the chain keeps one source per piece (bit-equal merges), the witness tracker fills left / right
  (`env_jit.track` / `track_beam`); the search's realizer then passes the keys through the game's hold filter (3.4.2).

#### 3.2.6 Bounds (the lead, 2026-10-22, asked by the person)

- TIME: the standard horizon 2 s = 120 f = 100 steps (it covers a jump cast from its Jump Aim to the end of the burst,
  55 + 65 + ~8 = ~128 f, and the trap lead times); the exact online part to the candidate's next branch point
  (typically 10 - 40 f); the long check stretched to 3 s (180 f) only while a jump cast is in its antic; the enemy
  predictions the same horizon with at most two future enemy choices branched. Measured: in the recordings the last
  safe exit vanished 25 - 40 f before an HP loss (11 of 15 losses, p50 25, p90 30) [M3]; the chosen plans' frames to the
  last contact 54 / 94 / 136 (p50 / p90 / p99) [M3].
- SPACE: the arena - the Forum walls x 14.01 .. 48.99 (35 u), the floor y 3.015 to the ceiling step ~15.15 (~12 u); the
  relative tables span x +-35 u and y -12.2 .. +9 u; other rooms from their terrain map.

### 3.3 L3 - the search [ON]

#### 3.3.1 Candidates and windows

- One decision (`Searcher.decide`) [M3]: predict() under her do-nothing path; NODES = her exact state at a frame, the
  plan so far, the Clappers re-predicted after its hits; expanded to depth 3, beam 4. Per node: the passes from her
  exact state (<= 1 event / 60 f and <= 2 events / 30 f) in the union danger of the branches (margins on) + the walls;
  the WINDOWS BOUND TO THE ENEMY intersected with the clusters' end-condition bits -> press points -> witness keys; safe
  endpoints; the library's macros when given. A landed strike makes a child node (the pogo bounce, the Clawline's
  control).
- WINDOWS ARE BOUND TO THE ENEMY (the person, 2026-10-20): time relative to its event, position relative to it and its
  facing; at decision time transformed to map coordinates with the predicted enemy state; the Clawline's PRESS region
  (in front of its body within the ray, her held box bottom in the band against its body, the press frames - e.g. slam
  antic 5 - 11) is checked against her envelope with a usable state; after the press the Clawline is a deterministic
  block. As built (strike.py): per branch, Clapper and frame the down slash's press region on its ROBUST body (the
  intersection over the timing variants, both sides of its centre) and the hooked Clawline's ray / height band. The
  exact down slash SHAPES (3.6): as built their windows are ADDED to the predicate's behind `Cfg.shapes` (default off;
  tables on only) [T4, code].
- BRANCH POINTS = the end of her discrete commitments (a slash's lock, the Clawline's control, a pogo contact / its
  i-frames' end, the umbrella's opening end, a jump release, a landing) and the enemy's reveal frames (its move choice
  visible on the antic's first frame - a Clapper's move start is a branch point: the lead's answer to the person's
  question, 2026-10-23 07:50). Continuous controls (left / right, the jump hold, the umbrella timing, the drift) are
  parameters inside a segment.
- PRESS VALIDITY (S1 / S1b, `ssbot.map2.press`; the airceil verifier's finding): a strike is credited only where the
  game would start it from the concrete kin state at the press - a down slash starts at the press or from the attack
  queue up to 7 f later (the air sprint's Attack Cancel); a press held only by kin's downspike lock is credited from 12
  f after a pogo's onset, 10 f after a hooked Clawline's forced bounce; a Clawline only where `env_jit.claw_allowed`
  holds and outside the lock (control + 13); the realizer keeps the witness's held jump / dash on the press frame or
  holds down through the sprint's cancel, else rejects the witness; a contact needs 0.05 u slack (both alternations
  meet the robust body box shrunk by 0.05 u, `ds_shrink`); the body's highest top of the frame's records is used
  (`union_tops`); a down slash's side contact out of the air dash / sprint is the BODY's - a forced collision, no pogo
  (`side_rule` 'lag': her hurtbox carried 0.5 u ahead in her travel direction against the body from the slash's start
  to its contact; the extra velocity counts from |XVX| >= 1 u/s); a bad press at or before the deviation frame makes
  the outcome unsafe.

#### 3.3.2 The closed-loop evaluation and the reveal rule

- (`Evaluator.evaluate`) [M3]: the concrete keys simulated with HERO2 + the strike module against each branch; a hit
  that can change a Clapper (on Idle, in a move's last frames, killing) re-predicts, and the branches consistent with
  the history carry on. Outcomes = branch x timing view (early / late) x hook variant.
- THE REVEAL RULE (the commit / reveal / reactive steering; the person's design, 2026-10-20): a candidate must be safe
  for EVERY enemy outcome during its committed part, with her reactive steering after the reveal + 1 - 2 f reaction
  lag; after the committed part every outcome must still have a safe continuation (the exit check). As built: her
  hurtbox vs the branch's damage (margins, not in the pogo i-frames, the hooked body harmless P + 17 .. control + 12);
  a collision before the branch's reveal + 2 f is unsafe, after it allowed if an exit exists from that frame (her hits
  after it do not count); a Clawline block delays the deviation to control.
- The latency in every 'safe until she can react' check: STATE arrives 1 - 2 f late, keys are sent 2 f ahead, the 50 Hz
  / 60 fps jitter, host stalls (the lead, 2026-10-20).
- TWO ENEMIES ARE A JOINT STATE (the lead, 2026-10-20): predict() takes both and branches jointly (bounded: the locked
  one has no new move until the other's lock ends). THE ENEMY'S CHOICE MEMORY (V4 counters; after Evaded only SLAM /
  CAST; the escape jump alternates 1:1) is modelled, so the outcome probabilities depend on its recent choices - the
  search can exploit it (the lead, 2026-10-20).
- `tick_check` = the closed-loop evaluation without its exits (M3's version, which predicted with none of her hits over
  the plan's length only, was a defect) [M4b].
- The evaluation is about half of a live decision's time (2.2); speeding it is the ev workflow's E1.

#### 3.3.3 Contingent plans [M3]

- A hooked Clawline whose hit splits the future into reactions gets one child node per reaction (p >= 4 %, <= 4),
  each with only that reaction's branches as its danger (with the union of all reactions every cluster at the
  Clapper's face died in the first frame), evaluated conditionally. `reaction_key`: the Clappers' choices made in P + 7
  .. P + 21 (the earliest control P + 23 minus the 2 f lag) and revealed by then. `_combine`: per reaction the best
  continuation (its exits checked) joined into one plan - the most probable reaction's as the default, the others in
  `Seg.out_alt` - and evaluated whole; a failing reaction falls back to its next continuation (twice), else the plan
  ends at control there. Only hooks split today (M3 open item 3: a down slash's hit on an Idle Clapper too).
- The lead's stronger fix for the reveal latency (not built): contingent continuations per Clapper reveal - the plan
  in control already holds 'if the slam starts at frame k, press the Clawline at k + 5 .. 11' (2026-10-23 07:55).

#### 3.3.4 The exit check and the escape funnel

- WHY: after the committed part every outcome must still have a safe continuation - this is what catches the jump traps
  set at Jump Aim 38 - 45 f ahead (SP14) [spec].
- AS BUILT (the exit check) [M3, M4b]: from the plan's end / the deviation an M1 pass (40 f, <= 1 event) in that
  branch's danger must keep a cluster - stretched to a big rune's last lit frame when one is pending (up to 180 f).
  EXIT PROBES first: 8 constant key sequences within the pass's one event rolled by the reference model; one touching no
  box is an exit (75,861 probe exits, 0 violations); an exact exit memo.
- THE ESCAPE FUNNEL AND ITS KEY NODES [DESIGNED] (the person, 2026-10-24: 'the 180 f search is there to see the trap and
  find how to run; take the key nodes out of the found route, then optimise - strike on the way to the nodes'): once per
  decision (per branch until the reveal, then the revealed one) push the tables BACKWARD from the region still safe at
  the long horizon (<= 1 event, 120 - 180 f): per frame the set from which she can still escape - a FUNNEL. Its narrow
  places are the key nodes ('under the jumping Clapper at frame 40', 'left of x 20 by frame 90'); between them it is
  wide and she strikes freely. Every strike candidate's exit check becomes a LOOKUP - its end state inside the funnel at
  its end frame - instead of one envelope pass per candidate (hundreds per decision). Recompute after each hit that can
  change a Clapper. A FACT FOR ITS BUILD: a funnel pushed backward with `bridge.backward` is exact only without the
  float's inertia - with it an upper bound, so its 'inside' needs `Back.exact` or a forward confirmation [T4] (Q10).
  An interim offline trial and an eps(k) fit exist in T4's data (2.1; not reported).
- THE SHRINK GROWS WITH TIME (the person, 2026-10-24: 'near-term exact, far-term a little error'): frame k of the funnel
  shrinks by eps(k) - the measured p99 deviation k frames after a sync (M0 / M4a frame-by-frame trials), ~0 near, larger
  far - and the danger grows likewise with k; the far part is recomputed from fresh observations many times before it
  is used. SAFETY VALVE: if the shrunken funnel closes but the exact one is open, run the exact one (a thin way beats
  none) and flag the decision for an early re-check. What does widen far out is the enemy's branching (the union of its
  later moves) - a prediction matter, met by recomputing on each reveal.
- The 'dev' end (a plan ending at an outcome's deviation): the exit's keys as the plan's own tail is not built;
  mitigated by `dev_gap` 6 (no commit when a possible 'dev' outcome is closer than 6 f to its collision) [M4d].

- THE AIM AT AIM TIME - A GAP TODAY (the person asked 2026-10-24: 'the old planner computes where to stand when the
  Clapper aims, incl. the inescapable zones at aim time - who does it in map2?'): the old planner has the AIM ZONES
  (forum.md 40 - 42; knowledge aim_zones_CC_JUMP / CC_JUMP_CAST / ...json: per aimed move, height and terrain band,
  the places from which, once it aims at her, no escape exists). In map2 nobody does this explicitly: inside a plan the
  Clapper model aims from her planned path (right), but BEYOND the plan's end `search.hero_path` holds her last
  position, so the next aimed move (the Jump Aim from her x, the Close / Far choice) is aimed at that frozen spot and
  the exit check / funnel tests escapes against a danger that does not follow her as she runs - it can call a trap
  escapable (she runs, but live the jump would land on her escape path). FIX (E1, with the funnel): AIM-AWARE exits -
  at each predicted aim frame inside the horizon the aimed move's danger is conditioned on her position at that frame
  (per x interval of the escape set: the aim follows her), i.e. the aim zones recomputed with map2's model per
  situation, or precomputed per (aimed move, aim frame, her height, wall band) relative to the Clapper like the old
  tables; their 'no escape' intervals become the score field's far-negative intervals of the long-term planner (3.7),
  whose aim nodes are the positive side of the same computation.

#### 3.3.5 The value

- AS BUILT [M3]: hits + the terminal value (wall room, the facing-to-the-wall rule +-0.5, the distance to the nearest
  body) - 0.002 per frame; expected over the outcomes; safe = every outcome safe; HITLESS FIRST: a plan must be safe for
  every outcome, hits rank the safe ones (the lead, 2026-10-20).
- TO BE REPLACED by the long-term planner's score of the plan's END CORRIDOR (3.7): the strike planner ranks safe
  candidates by its strike value + the minimum score over its end corridor, so a weaker strike ending well can beat a
  stronger one ending pinned (the person, 2026-10-24) [DESIGNED].

#### 3.3.6 The anytime order, the budget and its shape

- HYSTERESIS (the spec, from the G-line flicker of 10-12 / 13: templates rotating every 1 - 3 f): keep the chosen plan
  while its re-rolled key points stay inside the window's tolerance; a key-change penalty is allowed. As built [M3]:
  the kept plan, shifted and re-evaluated first; a new one must beat it by 0.05 (in live: `w_switch`) - this margin
  stands in for the tolerance rule; a key-change penalty is not reported as built.
- THE SPEED TARGET (the spec): the per-frame part p99 <= ~10 ms (met: TickCheck w7 p99 1.3 ms), the long search in the
  background between branch points, a time cap with the fallback to the committed plan (if its check still passes) or
  the default planner; re-plan every tick (receding horizon). As built: the newest snapshot goes to each idle worker
  (3.4.1) and `rev_cut` sends one to every worker at a Clapper's move start (3.4.7) [M4c, M4d2].
- ANYTIME DEPTH SLICES: depth 1 may use 45 % of the cap, depth 2 up to 80 %, each beam node an equal part of what is
  left; candidates round robin over primitive x Clapper [M3].
- `Cfg.live()` [M4b]: the 2-event pass on a background thread joined after 6 of the first pass's candidates
  (`pass2_after`, `pass2_bg`), the passes threaded (`fwd_threads`), the noop = the root's evaluation (`reuse_root`), its
  exits deferred (`defer_noop`), a HARD CAP (exit checks and evaluations stop at the cap; an evaluation abandoned
  before its next re-prediction), THE SPLIT SEARCH (`Searcher.part = (i, n)`: each of 2 processes takes the root's
  candidates whose key hashes to its part and their subtrees; the better result wins - a part combines only its own
  plans), a virtual clock (`vclock`) for deterministic runs. Tried and dropped: `safe_ts`.
- T4's search switches [code, T4 interim]: `Cfg.exec_only` (default True at the worktree head, absent from the frozen
  checkouts c0329d2 / f27ac9c: the passes and exits keep to the bot's executable family `env_jit.OPT_EXEC` - no up
  slash, free attack or hidden jump press, whose keys hold a slash the live controller rejects as unplanned);
  `Cfg.shapes` (default False; 3.3.1); `Cfg.h_pass` (the predictions reach the plan's end + the longest pass, so every
  pass's frames see the Clappers' danger; the default passes 60 / 30 f are unchanged by it).
- THE BUDGET SHAPE (the person, 2026-10-24): long horizon = few events (the exits, the traps: <= 1 event, 120 - 180 f);
  many events = short horizon (goal-directed chains toward a window, < ~1 s); no '3+ events x 120 f' passes (3.2.4).
- A 'to verify' flag: a plan relying on an untested mechanic is marked and goes to a forced trial before live use (the
  person's design, 2026-10-20; M4a was that trial for M3's plans).

#### 3.3.7 The strike module, the combo library, recognizers, logs

- THE STRIKE MODULE (strike.py): the down slash contact (both alternations against the robust body; the recoil), the
  pogo bounce, the hooked Clawline (the ray, the hold height, the stop, the control and its forced bounce, the
  harmless window), producing the next steady state (an apex or the ground) with its time and position - the apex is
  never an end condition of a table (the person, 2026-10-20). What can be hit and how (pogo-able / tink / pass-through,
  the enemy's invulnerable states, her recoil and its push) lives here (the lead, 2026-10-20).
- THE COMBO LIBRARY (knowledge/1.0.30000/enemies/forum/combos/<NAME>.json, combos.py): name, zh, status (candidate /
  verified / promoted / demoted), source, evidence, anchor (a Clapper state and its frame range / a bomb ring),
  preconditions as ranges, steps with timing windows and grids, branch points, uncertain mechanics, impl.
- EVERY EXECUTED PLAN IS LOGGED in the same step format (`plan_log` / `plan_steps`: per segment its anchor, key changes,
  strike events, a contingent plan's per-reaction continuations; value / hits / p_safe; the top outcomes) - for combo
  mining later. The move timelines and window tables live under knowledge/1.0.30000/<enemy>/ (npz).

### 3.4 Live control [ON in m2]

#### 3.4.1 Workers, snapshots, the bridge and the root prefix [M4c, M4d2]

- `SSBOT_FORUM_MAP2=1` (raises unless SSBOT_FORUM_HERO2=1 and the crest is Wanderer); off: nothing of `ssbot.map2` is
  imported and every hook is a `self.m2 is not None` branch. `SSBOT_FORUM_MAP2_SET=k=v,...` overrides LiveCfg.
- WORKERS: 2 search processes per instance (the split search), High priority, EcoQoS off, on the E-cores 16 - 31 by
  default (on the P-cores they slowed the bot's tick 4 - 6 ms p50; arm m2p), numba 2 threads (also in the background
  pass), `Cfg.live()`; warmed on a virtual clock (cold ~3.5 min, hot 2 s); a watchdog; they exit with the bot.
- A SNAPSHOT (sent only to an idle worker; with `sync` the same snapshot to both parts once both are idle): her kin
  state at the observation frame, the commands in flight, THE BRIDGE (the keys the bot expects to send while the search
  runs: the plan in control's keys up to `ch_lead` 40 f, else the fallback planner's own plan up to `fb_lead` 16, else a
  script's held key up to `sc_lead` 8), the hold filter's state, the Tracker's observation / Memory / hazards, the
  Clawline control (for the lock), the plan in control. Not sent while a slash's contact may still come, in a Clawline's
  block, a freeze, the intro, with no Clapper.
- THE ROOT PREFIX: the keys in flight + the bridge (through the hold filter, with the plan in control's down slash
  presses and their targets) form the root (`Searcher.root`); the noop = the prefix + one frame.
- THE CAP: `deadline` - the frames to the plan's root less `dl_margin` 3 less the wall time since the snapshot;
  `wait_parts` - a received plan waits for the other part until its root; `first_send` - the first safe plan, then each
  one better by w_switch, goes out at once (anytime).
- The kept plan (hysteresis): the plan in control re-anchored, else (`carry_f` 40 f) the worker's last plan not taken.
- MORE COMMITTED PLANS: `short_fix` (a press right after the bridge is not 'too short'), `alt_noop` (when the best is the
  noop, the best safe non-noop within `alt_slack` 0.3 is sent), `noinput_kin` (the umbrella / sprint / skid 'no input'
  frames are the hero model's own states and block nothing), `unsafe_short` (after 'unsafe', the short bridge).

#### 3.4.2 The hold filter (the realizer) [M4c, M4d]

The search's masks are latched masks and M1's witnesses press / release keys for one frame, which the oracle's hold
filter cannot latch (a press and a release last >= 2 f; a one-frame dash press to cancel the umbrella dashed 4 u). So
every plan is turned into what the game will receive before it is evaluated (`HoldRealizer` = `Searcher.realizer`,
`kinematics.hold_filter` compiled): the prefix kept, the rest through the filter; a down slash press moved to its
latched frame or dropped; a Clawline modelled exactly as sent from P, its press moved 1 - 3 f later with the direction
alone first when at P it would not latch as a rising edge facing the target. The acceptance at the same budget is
unchanged by it. The engine should offer only filter-feasible keys (M4c open item 7).

#### 3.4.3 Commit [M4c, M4d, M4d2, S1]

`commit_check` on the bot's thread before the planner: a received plan RE-ANCHORED to now (its played frames dropped,
the keys in flight and its own commands from f + 2 through the hold filter), re-simulated with HERO2 + the strike
module + the press rules from her observed kin state in every outcome consistent with the Clappers now (each matching a
record of its branch anywhere in its timing spread); committed only when each stays within `tol_commit` 0.2 u of its
planned path and touches none of its danger to its committed end. Rejections: 'clappers', 'path', 'danger',
'expired', 'unplanned slash', 'unplanned Clawline', 'press moved', 'in a Clawline', 'slash under way', 'claw latch',
'ended' (a possible outcome's committed part already ended), 'dev gap'; no commit while she has no control; a plan
older than `stale` 45 f is dropped. A replacement of the plan in control must come from a search that had it as the
kept plan, or the plan in control is ending. `repair`: a plan whose bridge was not followed is re-simulated from the
keys actually sent (`tol_repair` 0.3 u).

#### 3.4.4 Execution and the possible outcomes [M4c, M4d]

Per tick the command for f + 2 of the most probable POSSIBLE outcome whose committed part reaches f + 2. An outcome is
POSSIBLE until the observation contradicts its OWN timing view's records (state, frame in it within tol_j, x within
`tol_x` 0.35 u, the facing; sticky for the plan in control) or its Clawline control (she has no control from P + 3 to
an outcome's control and has it from control on); none left -> all consistent ones count. THE PLAN ENDS when any
possible outcome's committed part has ended (the reveal rule's deviation). Possible outcomes disagreeing on a key send
only the bits they agree on (no press none is sure of). Her position within `tol_hero` 0.2 u of the re-simulated path
(not checked inside a Clawline's block to control + 2); off it with the Clappers consistent -> RE-ANCHOR (the commit
check from her state now, `tol_reanchor` 0.5 u) or drop. The tolerances are guesses, not calibrated (Q8).

#### 3.4.5 Drops, the late check, a newer search's verdict [M4c, M4d, M4d2, S1, S1b]

- DROPPED on: no possible outcome ('fail:clappers'), her off the path ('fail:hero'), the committed part's end, a freeze /
  slow-time / long frame (any frame since the previous tick with dt x 60 outside 0.9 .. 1.25) or her hit on a skipped
  tick, the supervisor's keys or pause, a newer search's verdict (`unsafe_drop`: the plan in control evaluated unsafe
  from the newer snapshot -> 'unsafe'; else cut after that search's bridge -> 'cut'), the late check.
- THE LATE CHECK (`late_check`, `late_base`): a frame whose tick was skipped holds the previous ACTION, so a plan's key
  change can come a frame late; when one of its keys slipped, the plan is re-simulated from the commit's own base (the
  state the commit checked it from) with the keys actually applied (its down slash presses moved where the keys latch
  them, up to 2 f; the Cogfly keys stripped) - dropped 'late' when a possible outcome collides, its Clawline latches
  late, or the slip moves her > `tol_late` 0.5 u. An ACTION applied late by the oracle is not seen (S1 open item 3).
- AFTER A DROP: `drop_keep` (after a drop on the Clappers / her position / its end - 'clappers', 'hero', 'end',
  'end_dev' - the searches from its bridge go on, the fallback holds that bridge, fb_hold permitting, and a search that
  kept the dropped plan sends it back, re-checked at the commit) [code: live.py]; `drop_rev` (a drop on the Clappers /
  her position restarts the search at once with the short bridge).
- THE DROP RULE ON A ONE-FRAME TIMING SHIFT (the gate's P2 / P5) [DESIGNED; E2]: re-check the safety on the observed
  state and keep the plan if it is still safe (T3 open item 3); with the plan as a tube (3.4.8), a Clapper one frame
  late is 'still inside the time widening: keep it' (the person, 2026-10-23).
- RE-PLAN FROM MID-ACTION [DESIGNED; E2]: the search must re-plan from the state she is in, including mid down slash
  (entry from any state; the person's catch, 2026-10-23): a root that carries the swing in progress (its target, its
  start frame) so simulate credits its contact, and the controller's busy rule relaxed after a drop. Today after a
  drop with a slash in flight map2 gets the keys back only 30 - 136 f later (p50) [T3].

#### 3.4.6 The handover and the fallback [M4c, M4d2]

- THE FALLBACK = the w7 / w13 default planner (rnjb) and its scripts. While map2 has the keys the scripts are not
  stepped (slam_play, the Clawline chase, the cast stab, the low hop, the evade chase are aborted on the tick map2 takes
  the keys; TwoPlay yields; the air show is not stepped) and the planner keeps planning every tick from the keys
  actually sent, so when map2 drops a plan the fallback continues from the real key state (held keys held or released
  as its plan wants, a press in flight not lost, no press repeated). The supervisor's keys always win.
- `fb_hold`: while a search from the planner's bridge runs, the planner gets that bridge as its CONTINUE row, enveloped
  first and ranked first among its safe rows that keep the commitments; it leaves the bridge only when its own checks
  need a change, and a key off the bridge cuts that search.
- THE FALLBACK MID-SWING [DESIGNED; E2]: the gate showed the fallback, handed a mid-strike / mid-hook state beside an
  attacking Clapper, pressing jump (the umbrella - no bounce) or air-dashing into the lunge (P2, P3, P5).
- THE UNPREDICTED HOOK REACTION [E2]: a hook's reaction outside the plan's outcomes (the gate's P3).
- The supervisor still judges with the fallback's plan (res.S, FORCED_RISK) while map2 has the keys (M4c open item 6).

#### 3.4.7 The reveal (`rev_cut`) [M4d2]

A Clapper's MOVE START (Slam / Spell / Jump / Cast Slam Antic, Evade Scuttle: the antic's first frame) sends the newest
snapshot to every worker at once (busy ones too) with a bridge of `rev_lead` 6 f and cuts the older snapshots' searches;
not sendable within `rev_wait` 12 f: dropped. The reveal latency stays 20 - 25 f p50 (2.2): a plan that can press at
antic 5 needs its root by antic ~4 and its search done within ~3 f, while the first strike plan at a move start takes
70 - 250 ms [M4d2]. This gap is the reflex's (3.5).

#### 3.4.8 The plan as a tube, with steering [DESIGNED; in the person's handover priority of 10-24 ~10:40, not in ev's E2 as logged - Q24]

- ERRORS AS WIDENING (the person, 2026-10-23: 'now every position is an envelope - is the error easier to describe?'):
  small continuous model errors become one more widening of the intervals: her position error eps_x(state, k frames
  since the last sync) - the p99 deviation per action type in the M0 / M4a frame-by-frame trials -, the timing error as
  a time widening (frame t's set = the union over t - 1 .. t + 1: a late tick, a Clapper a frame early / late), the
  enemy's error as its margins and timing views. A PLAN = its path + that widening = A TUBE; safe = the tube misses the
  grown danger; executing, the plan stays while the observed state is inside the tube (instead of the hand-set
  tolerances and fixed timing views). Discrete alternatives are branched (3.2.2).
- STEERING INSIDE THE TUBE (the person, 2026-10-24: 'are the planned routes all with width?' - not yet; today the search
  commits one key line per outcome with hand-set tolerances): the committed plan = its discrete events at their frames
  + per frame an x corridor (its own envelope with those events, left / right free, cut by the danger, shrunk by
  eps(k)); each frame the left / right inside the corridor is chosen to keep off its edges and correct the drift; the
  presses keep their frames.

#### 3.4.8b Two tiers - a per-frame map2 tier as the baseline plan (the person, 2026-10-24: 'can the new planner's
coverage depth be made the same as the old planner's?') [DESIGNED; E2]

- WHY THE OLD PLANNER ALWAYS HAS KEYS: it re-plans every frame (~12 - 16 ms per tick) over cheap candidate rows with
  precomputed danger (the aim zones, the slam map) and always takes its best row, proven safe or not; map2 searches
  deep (0.1 - 1 s per decision, the Clapper re-predicted in closed loop, every outcome) and acts only on a plan safe in
  every outcome - so it hands back often (M4d2, strict w7: the worker's best was the noop 29 %, the search cut 28 %,
  the plan failed the commit 21 %, nothing safe found only 11 %).
- THE DESIGN: TIER 1, per frame, the same depth and speed as the old planner but with map2's model - a short horizon
  (<= 1 event, ~60 f), the tables for her reach, the danger precomputed per Clapper move / frame (E1), the exit as
  the funnel lookup, within a few ms - always outputs keys: the BASELINE PLAN (Q2), the least-risk escape when
  nothing is proven safe. TIER 2 = today's deep search in the background (multi-event, contingent plans, strikes):
  when it finds a plan better than tier 1's it commits it (the tube) and tier 1 yields. TIER 0 = the reflex for the
  latency-gap windows (3.5). The old planner then only covers states the model does not know.
- BETTER THAN today's 'hand the keys back to the old planner' (one model everywhere; no handover between models
  mid-swing - the gate's failure mode) and than E2 (e)'s first form 'commit the deep search's noop / escape' (that
  answer is only as fresh as the last deep search). Measure: tier 1's per-tick time on the bot's thread / a worker,
  the share map2 holds, collisions 0, invalid presses 0.
- TIER 1 IS MOSTLY LOOKUPS (the person, 2026-10-24: 'her current state has a table with the reach of every later
  frame - finding a point next to the damage boxes should be fast'): split the danger by whether it depends on her.
  INDEPENDENT of her (most frames): once a Clapper has chosen its move (a slam, a cast, a jump's landing), its damage per
  frame is fixed up to its timing views - reach (the tables) minus that danger per frame is the safe set, a strike /
  safe point is an interval intersection, the keys come from the chain: sub-millisecond and EXACT, no closed-loop
  re-evaluation. DEPENDENT on her (a few moments): a Clapper's choice / aim frame inside the horizon (Close / Far by her
  distance, the Jump Aim from her x) and her hits that can change it (an Idle hit's reaction) - only a candidate whose
  path crosses such a moment needs the re-prediction, split by her position interval at that frame (the same
  computation as the aim-aware exits, 3.3.4). Today every candidate is re-evaluated in closed loop over its whole
  length (~15 ms each at 1 s: T4's 64 candidates) even where the Clapper's move is already fixed. Needs the danger
  precomputed per Clapper move / frame (E1 (b)).
- PROBABLY NO TIER 2 (the person, 2026-10-24: 'very likely tier 2 is not needed - add the long-term planner for
  switching targets and the long-distance escape, that is enough'): an event is a motion key, an attack is not, so
  most strikes are ONE event (a hop + down slash, a Clawline + the slash after control, the umbrella close + the
  strike, a jump + the ride's slashes); a sequence becomes a chain of one-event plans re-planned every frame - after a
  hook the reaction is revealed at the needle's hit (P + 8 / 9), 15+ f before control, so tier 1 plans the follow-up
  then, no contingent plan needed; the long-term planner (3.7) keeps every step out of dead ends (the funnel) and
  steers toward places with a follow-up (the score field), and does the target switching and the long escapes. Keys
  that must be pressed inside a transient (the air sprint's attack / jump cancels, the sprint jump) are variants of the
  one dash action in the bundle. CHECK BEFORE DROPPING TIER 2: tier 1 alone, re-planned every frame in closed loop,
  on M3's acceptance situations - which of P1 - P5 and the regression moves still come out, vs the deep search; a move
  that does not marks a real need for a multi-event commitment. Until then no new work on tier 2 (its code stays).

#### 3.4.9 Logs and tools [M4c, M4d2, G]

The per-tick log `map2_i<N>.jsonl` (owner, why, plan id, frames since its anchor, committed frames left, the possible
outcomes' p, the search latency, dh / dc deviations, each commit / re-anchor check, the commit row, triggers, busy,
the worker's last message, map2's bot-side time; holds, cuts, reveal snapshots, audits); the decisions log's `final`;
per-episode stats. Tools: `forum_policy_replay --realtime / --map2-log`, `ssbot.tools.m4c_smoke run / report` (the
real-time replay smoke: strict = a plan committed only when the keys sent since its anchor were its prefix - the live
path check's proxy; open = her recorded position, tolerances only logged), `m3_accept`, `m4b_speed`, `ssbot.tools.m4_gate`
(check / report / trace; the gate's behaviour bars: still > 240 f, > 12 reversals in 60 f, kill > 40 s, > 16 owner
switches in 60 f). The replay's own artifacts (the Clappers react to the RECORDED hero; the recording's slashes push
them 0.36 - 0.48 u; the 'no input' / 'slash' busy frames are the recording's) bound the share a replay can show
(`replay_push` handles the push) [M4d2].

### 3.5 The reflex [OFF]

- ORIGIN (the person, 2026-10-23): the strike windows stored on the Clapper and a per-frame reflex on top of the bot.
- SCOPE (the person, 2026-10-24: 'the windows bound on the Clapper are for the fast reaction - only the first ~10
  frames the normal search is too slow for; later ones the search finds in time anyway'): keep in the reflex ONLY the
  windows whose last press frame falls inside the search's reaction gap after the reveal (~25 f today, shorter after
  the evaluation work): the Clawline into the slam's first window (press at antic 5 - 11; ~17 k full cells), the small
  rune's first-frame Clawline (~20 k), the chase of an evade's start (~5 k) - ~1 % of the table. Every other window
  goes to the search as a goal shape (candidate generation). (The cell counts = the v1 tables' full cells of claw_slam0
  G + A, cast_claw G + A, evade_claw G + A [RFX2].) WHY: the table covers every window of every move - 4.25 M cells,
  the bulk long windows the search can foresee from the reveal (the cast head pogo 2.37 M full cells, the slam head
  pogo 0.60 M) - and in the replays it fires ~28 / min, each fire an 8.5 - 150 ms safety check that competes with the
  search; the reduced scope is 100x smaller, needs far fewer runtime checks and gives no duplicate or competing
  strikes (the person, 2026-10-24).
- AS BUILT (branch reflex) [RFX, RFX2]: 11 window types (claw_slam0, claw_head2, hop_slam0, drop_slam0, pogo_head2,
  pogo_jantic, ride_up, ride_down, pogo_cast, cast_claw, evade_claw); the generator = the search's closed-loop
  evaluation judged strictly (lands / touches nothing / an exit in every outcome; one continuation per hook variant);
  the table `clapper_windows_v2.npz` (4,267,885 cells, 15.9 MB; key: dx 0.25 u on the ground, 0.5 u in the air, bb 0.5
  u, vy 2.4 u/s bins, float frames in 8-f bins; a Clawline window keyed by her hold height x a vy class; FULL / PARTIAL
  cells); the runtime `Reflex.check` (her state at f + 1, the lookup, the gates - attack ready, the Clawline free, the
  hold filter -, a check always from her exact state in a fresh closed-loop prediction of every Clapper under the
  macro's path, the strike re-derived in every outcome, the exit to a big rune's end) -> a `Press` (commands per frame,
  the continuation per hook variant picked from the control she shows).
- NUMBERS: precision on 16,130 live bot presses 0.999 (TP 9,457 / FP 8); the replay (520 traces, 251.5 fight minutes):
  28.5 fires / min, the first press judged exactly at f + 1 ok 99.5 - 99.7 %; the windows the bot left that the reflex
  takes: the small rune cast's first-frame Clawline 2.5 - 4.2 / min (the bot pressed it 0 times in 810 runs), the evade
  Clawline 1.4 - 1.7 / min (w13). Cost: ticks without a window p99 0.14 ms; the check p50 8.5 / p99 151 ms -> must run
  on a worker.
- INTEGRATION PLAN (after M4's gate; reflex.py's runtime header): on top of `Map2Controller._pre` before '1. commit' - a
  running Press plays `cmd_at(f + 2, ctrl_seen, dx_seen)`; else `Reflex.check(...)` with the controller's state, keys
  in flight, hold state, observations, Clawline lock and intro flag; a Press drops the plan in control and owns the
  keys to its end; `post()` sends its commands from f + 3 as the bridge; the check runs on a reflex worker along the
  bridge (the next ~8 f) and the thread fires a matching verdict (< 1 ms). Then a live smoke.
- Its relation to the shapes: the windows are to move onto the exact shapes after the tables (3.6); the built table is
  cell-based (Q13).
- WHAT IT SHOULD BECOME - AUTO-GENERATED FIXED ROUTINES (the person, 2026-10-24: 'what is needed is still fixed
  routines like before, but they must not be hand-made - they must be generated automatically'): the old scripts
  (CLAWSTRIKE, SLAMSTRIKE, LOWHOP, JUMPTRAP) were hand-made; the reflex table's 11 window TYPES and their macro shapes
  are hand-chosen too (only their parameters are generated). Generate the routines themselves: per (Clapper move,
  frame) x her relative state (as shapes, 3.6) an offline search over short key sequences (a few events, inside the
  move's window) keeps those that strike in every timing view, touch nothing and leave an exit; among them the
  natural-selection order (fewest presses, then the earliest strike, then the largest margin); stored as trigger
  shape + keys + outcome; validated on the live presses as the reflex was (precision first). Live: before the reveal,
  a worker checks along her planned path which routines a reveal would trigger and pre-runs their safety check against
  everything else (the other Clapper, lit runes); at the reveal the routine fires at once. The generated library can
  also replace M3's hand-made combo library as search candidates. Scope first: the latency gap only (above).
- IS IT NEEDED AT ALL (the person asked 2026-10-24; the lead's comparison): the need is only the reveal latency gap -
  the slam's first-window Clawline must be decided within ~0 - 9 f (0 - 150 ms) of seeing the antic, the search finds
  that plan in 70 - 250 ms [M4d2]. Rewriting in C++ does not close it (the hot parts are numba-compiled already: ~1.5 -
  2x at best vs the 2 - 5x needed). Three ways: (1) the routine / reflex lookup (its safety check must move before the
  reveal); (2) a faster search restarted at the reveal (E1, uncertain to reach < ~50 ms); (3) responses to the
  Clapper's possible moves prepared in the background before the reveal (the contingent plans extended from the hook
  reactions to its own move starts). (3) with the generated routines as its content is the preferred form; E1 / E2
  measure whether (2) / (3) fit the gap.

### 3.6 The strike windows as shapes (the person, 2026-10-23: 'aren't the windows polygons?')

- THE DESIGN: per (Clapper move, frame in it) x her EXACT vertical state (the table and its phase - A1_n step, float
  frame, bounce step: no vy bins) an x INTERVAL SET PER HEIGHT (the envelopes' and the danger's structure), mirrored by
  its facing, the walls clipped at use time; the boundaries found exactly by bisection with the strike module's judge.
  No partial cells (the reflex's 8.5 - 150 ms re-check was mostly the partial cells); the windows ARE the backward
  tables' goal regions (window x envelope = interval against interval). Built with the tables (their goal regions);
  the reflex moves onto them after.
- AS BUILT (`wshape.py`) [T2; wired behind `search.Cfg.shapes`, off, by T4] [OFF]: the down slash's PRESS REGION per press frame x her state at the press (her
  vertical after the press, the swing's run reach from her lanes, the facing mirroring the polygons): the x set of her
  transform from which both alternations meet the robust body box in press + 3 .. + 9 before she lands - exact
  boundaries, checked against the judge: points just inside 1,176 / 1,194 hit (the rest at a cluster's interval end:
  the shape unites both facings), just outside 0 / 268. Against the search's predicate (235 situations): the predicate
  406,428 windows, the shapes 513,231, both 402,839 - the predicate misses ~27 % (contacts at press + 5 / 7 / 8 / 9 it
  does not test) and has 0.9 % false ones (its 0.5 u slack, its extrapolated height). Not done: the hooked Clawline's
  shape (the ray's reach, the hold height, the control), the shapes as precomputed knowledge per (Clapper move, frame),
  the reflex's validation events.

### 3.7 The long-term positioning planner [DESIGNED]

- THE PLANNER (the person, 2026-10-24: 'the 180 f look-ahead is really a long-term positioning planner - besides the
  escape nodes it should tell the strike planner roughly where to stand and whom to hit; the hand rules should now come
  out of modules automatically'): on the escape funnel (3.3.4), a LONG-TERM VALUE per position from the model: (1) the
  ROOM - the funnel's width and its time to closure from there; (2) the STRIKE OPPORTUNITIES - the strike windows (the
  shapes) reachable from there in the next 1 - 2 s per Clapper under its predicted moves (whose windows dominate = whom
  to hit). It replaces M3's hand terms (wall room, facing-to-the-wall, body distance).
- PREDICT ITS AIM AND STEER IT (the person, 2026-10-24: 'predicting the Clapper's aim timing and steering it into its
  moves belongs to the 180 f process'): today the model has the aim rules (L1) and the search uses them only implicitly
  - each candidate's path goes into predict() within the plan's ~1 - 2 s - with one hand term (facing-to-the-wall). The
  planner does it on purpose: (1) predict each Clapper's next decision / aim frames from its state's timers; (2) for
  her candidate positions at those frames, the resulting choice distribution and the jump's landing spot, each valued by
  the long-term value; (3) the best place at that frame becomes an AIM NODE of the funnel, given to the strike planner
  with the escape nodes (e.g. inside Slam Range at its choice frame to draw a slam - a window -; its jump's landing drawn
  to the middle / under her for a ride / out of the corner).
- SCORES ON INTERVALS, THE STRIKE PLANNER DECIDES (the person, 2026-10-24: 'score intervals, not points; set the scores
  sensibly; the inescapable intervals get a large enough negative score; the strike controller chooses by its strike
  situation'): the output is a SCORE FIELD in the envelopes' structure - per frame and vertical state, x intervals each
  with a score, broken where the score jumps (each Clapper's Slam Range line, the funnel's edge, the window shapes'
  edges, the jump-landing boundaries); units: expected future hits minus the expected HP loss, the same as the strike
  value, so the two add; outside the funnel a score far below any normal one (never chosen while anything else exists,
  still ordered when nothing else does); the weights from the model, checked on the recordings (high-score places
  should be followed by more hits and fewer losses). Safety stays the hard rule (the tube inside the funnel); ranking
  as in 3.3.5.
- THE PERSON'S TWO-CLAPPER RULES ARE CHECKS the value must reproduce, not code: (1) stand between the two Clappers;
  (2) between them, hit the one farther from its wall; (3) when both must be on one side, pin them in the corner, never
  be pinned; (4) when they are far apart, drive the focus Clapper toward the middle. Measure per rule on the recorded
  two-Clapper situations whether the value prefers it; a disagreement means a missing mechanic (find it) or a horizon
  too short (rule 4 may need seconds: then a longer-term position term). Part of these rules may come out of the aim
  steering.
- THE KNOWLEDGE LAYER - DISTILLED OFFLINE (the person, 2026-10-24: ''stand between the two', 'drive the Clapper to the
  middle' are knowledge - maybe they need to be summarised offline'): the online value sees ~3 s (the funnel, the next
  1 - 2 s of windows); such rules pay off over many seconds (herding takes a while; standing between them makes their
  later moves easier for a long time), so they come from data: (1) a few configuration features - her place between /
  outside the two, each Clapper's distance to its nearest wall, their distance, the focus Clapper's distance to the
  middle, the facings, their current moves; (2) from the recordings (the bot's and the person's real play, never
  _excluded) the outcome of the next 5 - 10 s per moment - hits landed, HP lost - as a table 'configuration -> long-term
  value'; (3) the model's simulation where the recordings are thin (both pinned in a corner) and for counterfactuals
  (the same configuration played from between vs from one side); (4) the outputs: the table as the long-term
  planner's terminal value beyond its horizon, and a readable rule list with measured effect sizes - the person's four
  rules checked one by one, new ones possibly found. CLEAN MATERIAL (the person, 2026-10-24: 'the material must be
  clean - do not learn from recordings of a buggy controller that the positioning was bad'): the PRIMARY signal is the
  situation's quality by the model, independent of who played - per recorded moment the funnel's width and time to
  closure, the windows reachable in the next 1 - 3 s; the realized outcomes are only a check and are filtered by the
  cause audit first (an HP loss the audit puts on the controller - a handover, a script clash, an invalid press, a
  late tick, a planner error - is dropped; only losses where the model shows no escape existed count against the
  configuration); counterfactuals by simulation with an offline, generously budgeted search as the policy (only model
  error left); sources kept apart - the person's real play (cleanest, but their style), the bot's audited runs; never
  the gate runs (the handover bug), the no-landing show runs (another goal) or _excluded sessions. Cautions: the
  recordings' situations come from the old policy - re-learn from map2's own fights later; simulation error grows with
  the horizon. Cost: tokens only for writing / checking the tool (one agent, ~0.3 - 0.6 M); the counting itself is
  machine time; make it a reusable tool (features and windows as parameters) so later re-runs cost no tokens.
  WHEN (the person, 2026-10-24): recorded for later - do it once map2 can replace the old controller (3.8's criteria)
  and the positioning knowledge is needed; not before. The recordings part needs
  no code changes and can run beside other offline work (not during a profiling run); the simulation part with the
  planner.
- WHEN: 'next stage after the A1_n tables are in the search' [spec] (Q12).

---------------------------------------------------------------------------------------------------------------------

### 3.8 The old planner, map2 and the reflex - roles, and when map2 replaces the old planner (the person asked 2026-10-24)

- THE OLD PLANNER ('the hard-coded rules', the default arm rnjb) [ON]: hand-written rules and scripts (CLAWSTRIKE,
  SLAMSTRIKE, LOWHOP, JUMPTRAP, the chase / stab scripts, the TWO_* two-Clapper rules), with the person's OLD SPECIALS
  TABLE (forum.md 48 / 53, 2026-10-11 / 12: offline strike rows bound to the Clapper slam's antic frame and her relative
  position / vy class - v1 5,757 entries, v2 5,938 entries / 12,472 core cells, built in 5 s from T1's grid; the
  planner generates ~840 - 1,300 'walk to the cell, strike at its frame' rows per tick, 10 - 11 ms single-thread). In
  the m2 arm it is the FALLBACK (w7 ~65 % of the engaged ticks, w13 ~95 %).
- MAP2 [ON in m2]: the general planner from the model (L1 + L2 tables + L3 + live control). The old specials table's
  'where to strike, and the way there' is the search's job here: the window shapes as goals, the envelope / tables to
  reach them, the keys from the chain.
- THE REFLEX [OFF] = the old specials table's successor for the instant part only: it fires a routine when she is
  already inside a window, it plans no approach; its scope the search's latency gap (3.5). So the reflex alone does not
  replace the old specials table; map2's search + the reflex together do.
- REPLACEMENT CRITERIA (the lead's proposal 2026-10-24, to confirm): map2 + the reflex replace the old planner + its
  specials table when (1) map2 holds the keys >= 95 % of the engaged ticks on w7 and w13 (it always has a plan - the
  baseline plan of Q2); (2) in an A/B its hitless rate is not below the old default's (w7 13 - 15 / 16; w13 hitless
  clears 5 - 18 / 64); (3) the old scripts' moves appear live at least as often (CLAWSTRIKE, SLAMSTRIKE, JUMPTRAP,
  LOWHOP); (4) no handover / stuck problems. Then the old planner stays only as an emergency fallback for unknown
  states, and before retiring its specials table check offline that its entries and the old fixed-point successes
  fall inside the new window shapes / reflex cells.

---------------------------------------------------------------------------------------------------------------------

## 4. Cross-cutting rules

- EXACTNESS, NO SNAPPING (the person, 2026-10-21): tables and passes are exact (heights bit-equal, x within 1e-9 u in
  every exactness check); merges only on bit-equal states; nothing snapped; over-approximations are allowed only where
  documented (the list in 6.2) and the final exact simulation rejects what they let through - nothing reachable may be
  lost (a known exception: the engine's merge is not monotone in its options, a window lost in 1 of 80 situations - T2
  open item 7, 6.2).
- SWITCHES AND BIT-IDENTITY (the spec's stage rule): every new behaviour behind a switch, default off, and the bot's
  decisions bit-identical with it off - checked by replays (w7 192006 i0 e1 2,073 ticks, 084036 i1 e0 1,778; w13 144051
  i1 e0 1,541, 102908 i0 e0 1,659; the rnjb and M0 envs, HERO2 unset / =1) byte-identical to the base, and for the
  search by deterministic digests on a virtual clock. Nothing in the bot imports `ssbot.map2` (or the reflex) unless
  the switch is on (import tests).
- EVERY STAGE has fixed points / checks and a cause audit (the spec, 2026-10-20); stages are sequential.
- MARGINS FROM MEASURED ERRORS (the lead, 2026-10-20): every model (hero curves, enemy polygons and timings) carries its
  measured error; the checks grow the danger / widen the timing by it (per move, per frame offset); plans leaning on an
  untested mechanic are flagged. History: the air strike (1 / 5) and the special mode failed on model errors, not on
  search. Measured numbers in use: M2's look-ahead and M3's in-move margins (3.1), the contact slack 0.05 u, the
  sprint's x lag 0.5 u (S1b), the live tolerances (3.4.4).
- ERRORS AS WIDENING and eps(k) (3.4.8, 3.3.4): the near term exact, the far term shrunk by the measured p99 deviation.
- PRESS VALIDITY (3.3.1): no strike credited that the game would not start from the concrete state.
- THE SAFETY NET: the final exact simulation of the concrete keys before every commit; the per-frame consistency check;
  the late check; the replay audit (every control run re-simulated as sent) and the press scan in every smoke; the
  fallback (rnjb) whenever map2 has no safe plan, and unknown or rare enemy states fall back to the old conservative
  supports (the lead, 2026-10-20); the gate stops at the first problem; HITLESS FIRST (a plan must be safe for every
  outcome; hits rank the safe).
- MEMORY: bound the caches before long runs (the envelope pass's outputs copied out of its buffers: 8.1 - 48 GB -> 1.6
  GB, M4b); a worker with the tables 5 - 20 GB (T3); the library's growth budget with an exact reset.
- MEASURING LIVE (the lead, 2026-10-20): one 64-episode A/B cannot see small gains (the same default gave 18 / 64 and 5
  / 64); keep the default as a control in every session and pool. The share and the latencies depend on the machine's
  load (another worktree's 5 Idle workers cut the replay share ~9 points, S1b) - the gate wants a quiet machine (for
  the gate itself: Q23).
- SILK IS NOT A CONSTRAINT (the person): never a state, never planned around.
- ANALYSE EACH IDEA AGAINST WHAT EXISTS (the person, 2026-10-24): do the better ones, drop the equivalent ones - record
  the analysis (the decision log).

---------------------------------------------------------------------------------------------------------------------

## 5. Decision log (dated one-liners; S = superseded, W = withdrawn, N = analysed / deferred, not built, M = a spec
number replaced by a measurement, D = a decision; 'who' in brackets)

THE DISPOSITION LIST: C:/ssbot/data/m2_play/map2/design/disposition.txt maps every paragraph of the old spec (deb8c9f,
698 lines) to its section here, to a line below or to an open question in section 6.

- 10-19 D (the person) the facing steered by the down slash's contact side (face the wall, evades go to the middle) -> P3.
- 10-19 D (the person) the slam's two down-slash points, the first taken with the Clawline at antic ~5 - 11; above its
  head close the umbrella and drop into the ray band first; the Clawline on Idle + the ride + float over the landing.
- 10-20 D (the person) the hero's control as envelopes, no key enumeration; silk not a state; the five gaps P1 - P5;
  start Wednesday night; acceptance = P1 - P5 found by the search (spec 9603ecf).
- 10-20 S (the person -> the person) tables keyed by every controllable state incl. vy (ec3b4cd) and the lead's 'vy
  bins, hundreds of tables' -> junctions only at steady states (00bbfd6); 'compatible states' at the meet -> steady
  junction states.
- 10-20 S (the person) the table set '4 start states x 10 end conditions x 120 f, flag-byte rasters ~22 MB per start'
  (b49817f) -> walk / run steady, the apex only a start (40b95c5) and contour storage (2f70e73), same day.
- 10-20 M (the person) storage = 'a handful of contour vertices per frame' -> M1: p50 90 vertices / 13 polygons at
  frame 10, 697 / 51 at frame 30 (the dash / Clawline lobes); T1 stores nodes / edges and raster rows instead.
- 10-20 S (the lead -> the person) 'the terminal fall is kept only formally' -> it is reached (0.5 s / 7.5 u) (7f818e7).
- 10-20 S (the person) a landing as an end state -> terrain contacts are branch events (bc223ed).
- 10-20 S (the person -> the person) event frames on a 2 - 4 f grid refined near tight windows (b6b5189; also the L3
  'coarse grid then +-1 - 2 f refinement') -> the same evening: every frame is a possible event start, the merging
  absorbs it (f21950d).
- 10-20 S (the person -> the person) the vertical curves stored as 1-D arrays, 'no 2-D air tables' (b6b5189) -> the
  flattened 2-D union per start state and frame beside the chained tables (10-23); T1 built 2-D flattened rasters.
- 10-20 S (the person -> the person) each vertical piece kept as a FAMILY over its event time ('dashed at any frame in
  [d1, d2]' one piece), a danger cut splitting the event-time interval the only branching (9786789) -> one cluster per
  event frame, exact merges (10-21, 2858fba); grouping adjacent clusters by event time only an optional storage
  compression [not built].
- 10-20 S (the person) 'the first frame the envelope touches danger IS the branch time; restart from a waypoint in a
  steady state' (ec3b4cd) -> danger cuts x only, the cut pass continues (9786789); the search's nodes come from strikes
  (M3).
- 10-20 S (the person) 'the shrinking envelope of a fixed future time T as the commitment monitor' -> the per-frame
  check of the possible outcomes (M4b / M4d), the tube (designed).
- 10-20 S (the person) storage as contour polygons with SAT tests, mirror halving (2f70e73) -> as built: x interval
  sets per height (0.05 u rows), boxes / circles compiled + the hammers' polygons (M1, M4b); mirror halving not
  reported as built.
- 10-20 S (the person) A1 'the end of an air dash (vy 0)' and A3 'the float at its terminal -6 u/s' as start states
  (6567b88, 40b95c5) -> the air dash ends in a fall at some vy (M1 / M4a); A3 is a curve (10-21).
- 10-20 S (the person) 'the far part coarse (~0.25 u cells, 2 - 3 f bins)' in L3 and the coarse far layer with vy bins
  (c48f124, 4812c06) -> no coarse far layer (the person, 10-24, dd15db1: with <= 1 event the long checks stay exact and
  cheap; coarse cells would close real narrow ways).
- 10-21 W (the person -> the person) snapping: A3 origin heights to a 0.1 - 0.25 u lattice (ed7726e) -> snapping only in
  the online pass (c70c178) -> no snapping at all (6dc9740; the attribution fixed 683cf44).
- 10-21 M (the person) the closure 'over ~200 start states, a few MB' and '~470 air tables' (cbdcec1, fae5a6f) -> M1
  built 1,758 tables (43.2 MB); T1 / T3: the library does not converge (T2's 2.4 M nodes; +1 M per 15 s of play).
- 10-21 M (the person) the cluster count 'a few thousand alive, ~1e3 in the far layer' -> M1: 23,831 at 16 f from rest
  (286 without the air dash).
- 10-21 D (the person) the Clawline's cooldown becomes a table flag only if M0 finds one longer than its block (3f5afd3)
  -> M0: a 13 f lock, no key.
- 10-21 S (the person) A3 keyed by 3 entry-vx classes with a per-class 1-D table (d14a479) -> the float envelope with a vx
  interval (10-23, ced9c1c).
- 10-22 D (the person) the jump's wall push acts near the landing, the rise unaffected (184d3f2) -> M2: the roof.
- 10-22 S (the person) one back-pointer per table cell offline (b9e3409) -> back-pointers on full states only
  (aa6a0cc; the person found the flaw).
- 10-22 N (the person) steady-state tables + fixed action lists between steady states, the table keys under it, the
  natural selection of action lists (fewest presses; same-state comparisons; diverse survivors; tie-breaks without
  clearance) (a3f2166, a9ff682, 8164e43, 6399967) -> DEFERRED by the person ('not fully thought through; if the tables
  already built work, use them for now', e85e098); made concrete as the A1_n tables (10-23); natural selection never
  built (Q7).
- 10-22 ~11:10 D (the person) test the map live: 100 % hitless kills -> continue, a problem -> stop and wait.
- 10-22 M (M0) the Idle reaction '12 - 18 f after the hook' -> in the needle's hit frame P + 8 / 9, from her throw
  position (the 12 - 18 f was counted from her arrival / the decision tick).
- 10-22 M (M0) the unhooked pull '~5.7 - 7.8 u' -> 10.6 u to control at P + 32; it ends at A1 (no bounce) + the drift.
- 10-22 M (M0) the Deflate '2 f (SP13a) vs ~8 f (the air show)' and 'the attack in the float plays a Deflate first' ->
  the slash on the press frame with jump held; a press on the release frame lost; the Deflate 6 / 7 f.
- 10-22 M (M0) 'a re-open 13 f after a close' -> from release + 12 while >= 1.1 u up.
- 10-22 M (M0) the attack cooldown '19 f press to press' -> 18 f.
- 10-22 M (M0) the bounce 'contact box + 4.09 u, apex + 22 / 23' -> the pogo 3.74 u (apex + 21 / 22), the hooked
  Clawline's 4.09 u (apex control + 22 / 23).
- 10-22 M (M1 / M4a) the air dash 'vy 0 for 0.1 s at 28 u/s, then A1 at rest; +-2.8 u' -> 2 dash steps + a 14 f air
  sprint with cancels, control P + 17 / 18, 4.0 - 5.8 u.
- 10-22 M (M0 / M4a / T2) 'is the air dash restored by a pogo? - measure' -> pogo yes, hooked Clawline yes, landing yes,
  the unhooked Clawline no.
- 10-22 M (M4a) the hooked body 'off to control + 0.2 s' -> harmless P + 17 .. control + 12, hurts from + 13 / 14.
- 10-22 M (M4a) 'a jump in the pogo contact -6 .. +2 changes nothing, from +3 the umbrella' -> pressed at contact + 0 ..
  3 lost, from P + 7 (the slash's Bounce event) the umbrella in the press frame.
- 10-22 M (M0) the hooked Clawline's 'attack 9 f after control' -> control + 10 / 11; 'the antic hover ~8 - 9 f' -> the
  throw at P + 9 (unhooked).
- 10-22 M (M2) Slam Range '+-8.05, -4.46 .. +3.37' -> +-8.046, -4.454 .. +3.369 + 0.02 u offset (Jump Aim's 'travel
  0.916 x clamp(+-12)' stands: the landing rule in 3.1).
- 10-22 M (M2) the wall-push flight '43 - 47 f' -> 43 - 46 f; 'every start state faces her, turns >= 0.5 s apart' -> a
  move's start state always turns to her, only Idle / Walk wait the 0.5 s.
- 10-22 M (M0 / AC1) the float drift '4.4 -> 2.5 u in ~20 f with no key' -> a key released in the float drifts on ~3 u
  (8.5 -> 0 at 0.25 per step); the Clawline antic's '~1.2 u drift toward it' -> her vx x 0.975 per step.
- 10-22 M (M4a) the umbrella antic '6 f' -> 5 - 6 f (5 once their time reaches 5 / 60 s).
- 10-23 M (S1 -> S1b) the long pogo recovery '18 - 23 f' (S1: 14 of 361 bounces; kept in the spec's 10-24 example) ->
  15 - 23 f in 5 % of 1,292 bounces.
- 10-22 M (M3) 'SP14: the last exit vanished 23 - 45 f before a hit, p50 ~40' -> 25 - 40 f, p50 25 / p90 30.
- 10-22 N (M1) the far-layer BANDS (a superset by y / vy hull) - not used (50k - 290k clusters with the dash).
- 10-22 S (M3 -> M4b) M3's tick_check (no hits, the plan's length) -> the closed-loop evaluation without exits (a defect).
- 10-23 S (M4c -> M4d) the timing views matched together in execution -> possible outcomes and the plan's end at the
  first possible deviation.
- 10-23 N (M4b) `safe_ts` (safe endpoints at earlier frames) - tried and dropped.
- 10-23 07:50 D (the lead, the person's question) a Clapper's move start is a branch point; measure / cut the reveal
  latency (not met; not required for the gate, 15:40).
- 10-23 09:45 D (the lead) the gate's share bar >= 50 % of the engaged ticks -> lowered to 30 % by the person (15:40).
- 10-23 S (the person -> the person) the shared dash bundle with dash-version tables ('A1 x 2', de45530; the lead's point
  1 'A1 x 2 for the air dash flag') -> the air dash not in the tables, no dash versions (0ec3ca2).
- 10-23 S (derived in the spec, the shared-bundle bullet) 'a dash-version table = its no-dash twin + one bundle
  reference' -> removed with the above.
- 10-23 S (the person -> the person) into the float the reference splits by vx (709cf0c), three entry classes, ~59 x 3
  float tables (dc21182) -> the float envelope with a vx interval, one table per phase (ced9c1c), same day.
- 10-23 15:40 D (the person) the safety items first, then the w7 gate tonight at a 30 % share bar; the speed work
  (the reflex, the A1_n tables) after; the reveal latency not required; no M4f.
- 10-23 S (the lead -> the person) 'the ground dash is not in the tables either, its own bundle as a bridge, several per
  ground stretch' (b3d9a8f) -> the ground dash IS in the ground tables (the person, the same evening, bc452fa; the
  time: Q27).
- 10-23 19:29 D (gate) FAILED, stopped after 2 of 16 episodes; no fix tried.
- 10-23 ~19:50 D (the person) 'build the recursive tables directly' (T1 no-dash tables, T2 dash bridge, T3 search
  integration, two verifiers - ran 10-24 ~09:24 - 09:58 -, T4 fixes - running since ~10:07).
- 10-23 D (the person) entry from any state; errors as widening (the tube); the strike windows as shapes.
- 10-24 D (the person) long horizon = few events; no 3+ events x 120 f passes (T3 measured 2 - 26 s for 3 events).
- 10-24 D (the person) the escape funnel, eps(k), the safety valve; no coarse far layer.
- 10-24 D (the person) the long-term positioning planner, aim prediction / steering, scores on intervals; the
  two-Clapper rules as checks; the named hand rules of L3 ('focus / switch / herding, facing-to-the-wall, wall
  distance stay') to come out of these modules.
- 10-24 D (the person) the bridge's backward side only over the dash's end tables, B(window, end table) precomputable.
- 10-24 ~09:25 D (T3) the tables in the search are exact but not faster live; keep the switch off live.
- 10-24 ~10:40 D (the person; the lead's option 1, logged 10:50) the closed-loop evaluation and the handover first; the
  tables' state-recurrence fix later.
- 10-24 D (the person) steering inside the tube.
- 10-24 N (the person -> analysed) paths on flattened maps: 'C keeps (B, A) when B's stored source is not A' (5cdb272)
  and 'tag each flattened entry with its origin table and node' (ed916a9) -> both = entries keyed by the exact state
  with one source each = what the chain already does (bit-equal merges, one source per piece); storing it per start
  state does not pay (live states do not recur); not built (90b62e8).
- 10-24 D (the person) the reflex covers only the search's latency gap (~1 % of the cells); every other window goes to
  the search as a goal shape (deb8c9f).
- 10-20 M (the person / the spec's L2) 'the tables are a handful (ground, apex, float; x the dash flag)' and 'obstacle-free
  envelopes precomputed per mode and entry state, applied by translation' (forum_reach.npz the precursor) -> the memo
  library that does not converge (T1, T3); M1's canonical tables (built with M0's HERO2) never used, need a rebuild
  (M4a open item 4).
- (spec 1b.6) forum_reach.npz's TerminalValue as the terminal value's precursor -> M3's terminal value -> the long-term
  planner's score (designed).

---------------------------------------------------------------------------------------------------------------------

## 6. Open questions (not decided here)

### 6.1 Decisions the sources leave to the person, or where they disagree

- Q1 DECIDED (the person, 2026-10-24): no overlay eye check before the next live run - test live directly.
- Q2 DECIDED (the person, 2026-10-24: 'map2 needs a baseline plan'): map2 must always provide a safe plan of its own - when its
  best is the noop or nothing, it sends its safest escape (just running out of the danger, the exit / funnel's surviving
  path) instead of handing the keys back; the fallback only for unknown / unmodelled states. The next gate (the
  lead's proposal, to confirm): w7, 16 / 16 hitless kills with map2 holding the keys >= 90 % of the engaged ticks.
- Q3 EXPLAINED / PROPOSED (the person asked what it means, 2026-10-24): the offline acceptance runs the search on fixed
  situations and asks whether it finds the target move; more search time finds more (of 279 cases: 202 at 60 s, ~160 -
  183 at 1 s, ~80 - 87 at 0.25 s). Proposal: 'found' = found within the LIVE budget (the workers' caps: 0.25 s while the
  fallback has the keys, 0.6 s while map2 has them), with the 60 s run as the ceiling for reference.
- Q4 P3-FACE is never found (0 same in every run): the forced Idle Clapper evades / casts before she lands, so no contact
  is on an Idle / Walk Clapper; M3 suggests redesigned setups or a recognizer 'she is on its wall side when its next
  move starts'. Undecided.
- Q5 DECIDED (the person, 2026-10-24: 'turn them on; they are the main engine'): the A1_n tables are the L2 engine,
  on live (`tables=1`) from the next live run; T4 final: the tables-on search leads offline (1 s 164 -> 183 / 156 -> 181;
  0.25 s 76 -> 87; strict w7 share 33.1 -> 35.3 %, 0 collisions; behind at 0.15 s; the long pass off). The
  state-recurrence fix (a per-node terrain clearance, a shared memory-mapped library) and the workers' memory growth
  (T3: 5 - 20 GB per search process) become important; keep the memory cap. Frozen checkout C:\ssbot\live_1v1_499df40.
- Q6 B(window shape, end table) precomputed (the person, 10-24: 'the bridge check becomes a lookup') vs T2: with the
  danger touching her within ~8 f the chain is needed anyway; the backward set over the chain is cheap and exact
  without the float's inertia, an upper bound with it (Back.exact, T4); T3 did not wire backward sets because the
  forward rows give the same press points. Build it or not?
- Q7 NATURAL SELECTION (fewest presses) - deferred 10-22, never built; the reconstruction today takes the engine's merge
  order and the witness tracker. Is 'fewest presses, then earliest arrival' still the rule for choosing among
  equivalent paths?
- Q8 THE TOLERANCES AND eps(k): the stage reports give only whole-trial 'within 0.1 u' counts (M0 / M4a: 466 / 484,
  384 / 420, 899 / 928); an interim per-k fit exists in T4's data (a1n/t4/funnel/eps.json: the M0 + M4a trials, a
  sync every 6 f, p99 0.031 u at k 1 .. 2.59 u at k 60, per experiment type too) but is not reported; the live
  tolerances (tol_hero 0.2, tol_x 0.35, tol_j +-1, tol_commit 0.2, tol_reanchor 0.5, tol_repair 0.3, tol_late 0.5,
  dev_gap 6) are guesses (M4b open item 2); the tube design replaces them. T4 FINAL: eps(k) p99 0.03 u at 1 f, 0.51 at
  10 f, 1.24 at 30 f, 2.6 - 2.8 u from 60 f (p90 <= 0.02 u) - the far tail is wide; per action type still to be split.
- Q9 ANSWERED (the lead, 2026-10-24, the person asked 'weren't the Clapper's damage boxes done before? what does the
  old planner use?'): the boxes exist in several forms - the OLD PLANNER AS PLAYED (the default arm rnjb has
  SSBOT_FORUM_V2=1: combat.forum_v2, the w13 hitless clears of 5 - 18 / 64 came from it) tests rows against the
  ATTACK-RANGE ESTIMATE (combat.attack_range, the person 2026-10-10: per enemy family, branch and frames since the
  antic start the union of the real damage colliders of clean recorded instances, relative to the enemy, as a
  raster; its median displacement - the Clapper jump's landing from her offset at the antic start; margins m(type,
  k) from the error statistics added at decision time; an attack counts only once its antic is seen, idle bodies
  carried by their velocity), plus the aim zones for pending aims, the rune-bomb rows, the hit branch's reaction
  template and the escape-ready check - built once per tick and shared by all rows; the EARLIER planner (v2 off) used
  the EnemyTables + MultiForecast support (logged-branch unions, 0.05 u cells, 107 fights); move_data (SG1: per
  move, state and frame the damage / target boxes with timing variants - the slam map and the old specials table come
  from it); map2's Clapper model (M2: per branch and frame DAMAGE / BODY / POGO shapes with measured margins and
  timing views, her-dependent choices and aims). 'The danger per move / frame' (E1 (b)) therefore means USING map2's
  shapes the old planner's way: built once per decision per branch and shared by all candidates, re-predicted only at
  the her-dependent moments (3.4.8b 'TIER 1 IS MOSTLY LOOKUPS') - the old planner's speed with map2's exactness.
- Q10 THE FUNNEL'S PARAMETERS: 120 or 180 f, how many branches per decision, and how it meets the 'dev' end (S6's proper
  fix: the exit's keys as the plan's own tail) are not fixed; nor whether its 'inside' uses Back.exact or a forward
  confirmation where the backward set is only an upper bound (the float, T4). T4 FINAL (707 funnels): forward 4.2 ms
  warm vs the engine 23.7, backward 0.4 ms, 486 exact; but 407 / 570 open funnels CLOSE under the measured eps(k) (half
  by frame 30), and against the exit checks on 3,260 endpoints: agree 2,538, exit-only 678 (the funnel too strict), funnel-
  only 44 (must be explained before any use). So ONE funnel per decision cannot replace the exit checks yet; T4
  proposes a funnel per beam node (~5 ms each warm) - E1 takes it from there, with the safety valve (3.3.4).
- Q11 THE SCORE'S WEIGHTS: 'a score far below any normal one (e.g. worth many hits)' - no number; until the planner
  exists the value is M3's hand terms.
- Q12 / Q13 ORDER (the person asked 2026-10-24 'are the auto-generated routines the reflex? isn't it done?'): the reflex
  TABLE is built (11 hand-chosen window types, generated parameters, precision 0.999) but NOT wired into the bot, its
  safety check too slow for the bot's thread (8.5 - 151 ms: it must run on a worker before the reveal), its scope still
  all windows; the latency-gap scope (~1 %) and the auto-generation of the routines themselves are not done. Proposed
  order after the evaluation / handover work: (1) wire the reflex's latency-gap types of the built table (claw_slam0,
  cast_claw, evade_claw) with the pre-reveal check on a worker, then a live smoke; (2) the long-term positioning
  planner; (3) the auto-generated routines replacing the hand-chosen window types.
- Q13 (folded into Q12's order above) THE REFLEX: (a) the latency-gap scope (~1 %) vs the built v2 table (all windows, cells keyed by vy bins) - rebuild
  the kept windows as shapes first, or wire the v2 cells of those types? (b) '~25 f' reaction gap: the measured reveal
  latency is p50 20 - 25 / p90 43 - 55 f - p50 or p90 decides which windows stay? (c) its integration was planned 'after
  M4's gate' - the gate failed; when?
- Q14 THE REFLEX'S FOUR FINDINGS FOR THE LEAD, NOT CARRIED INTO THE MAP2 BRANCH [RFX]: (1) the Clapper model's physics
  steps are anchored to each prediction's frame 0, so the search / TickCheck / commit check predict a moving body a
  step off 5 of 6 times (`reflex.clapper_steps` gives hers); (2) with the anchored steps the judge loses 1,060 live hop
  successes, precision unchanged (the timing views shift records without the physics); (3) steps_of's phase mapping is
  wrong in 2/3 of the phases (no measurable control error); (4) a killing pogo bounces (77.6 % live) but the model
  drops the killed body and with it the contact (the search counts a kill as a miss). None appears in the map2 open
  items.
- Q15 THE SLAM ANTIC LENGTH (the gate's P2 / P5): every outcome of the two committed slam strikes was the 'early' timing
  view; why no 'late' view was among them (the timing spread conditioned on the frames spent, or the commit's selection)
  is not explained.
- Q16 THE HOOKED CONTROL FRAME by convention: the spec's 'control +26 - 34' (and MOVES_TODO's 'hooked control P+26-34')
  counts from SP13's P (2 f earlier than M0's); M3 uses 'the earliest control P + 23' in M0's convention; the spec's
  hooked 'dash +19 - 22 at 70 u/s for 3 - 7 f' is in SP13's convention too and no stage restates it in M0's. One
  number per convention is needed.
- Q17 THE DOWNSPIKE RECOVERY AND THE SIDE CONTACT: kin's DS_REC 15 / 16 f vs the game's 9 - 11 f (15 - 23 f in 5 %) after
  a pogo and 1 f after a hooked bounce (S1b credits from 12 / 10 f); the side contact out of the air sprint is a forced
  collision with a 0.5 u lag from recordings - both wait for a live probe (S1 open 1 - 2, S1b open 1, 3).
- Q18 THE FALL LATTICE: the spec's max fall 30 u/s and 'A1 ~31 phases' vs T1's 26 distinct lattice vy (A1_0 .. A1_25)
  then A4 at -31.2 u/s, and the flattened layer's '31 A1_n' tables.
- Q19 IDLE'S DURATION: the spec's 'Idle 0.65 s -> Walk' vs M2's 'Idle Time read at the Idle entry (1.15 s with a living
  buddy)'; the solo value is not restated by M2.
- Q20 RESOLVED (the lead, 10-24): the ev workflow has NOT been launched (only its PROGRESS header line exists); it
  starts after T4 ends and after the person has read this document. E1 carries the funnel, eps(k) and the shapes, and
  builds on T4's interim funnel / eps(k) trial and `Cfg.shapes` (read them first, do not redo them).
- Q21 DECIDED (the person, 2026-10-24): the no-landing show is NOT a goal of map v2. (If it is ever done: the lead's
  analysis prefers a negative ground score in the long-term planner's score field - hitless > no landing > hits - over
  a fake damage box on the floor, which would make a landing equal to a real hit.)
- Q22 RESOLVED (the lead, 10-24): '0.38 vs 1.9' was M4b's INTERIM run (map2/m4/m4b/final_runs.log, 'afterE', 04:57 on
  10-23, rec w7 one Clapper); M4b's final numbers replace it: 0.79 at 0.25 s vs 2.13 at 60 s.
- Q23 RESOLVED (the lead, 10-24): the reflex_build jobs were SUSPENDED (psutil suspend of both process trees, 12
  processes, 'stopped') from ~19:25 to 19:45, covering the gate (19:29:54 - 19:31:06); they still existed, which is why
  M4_GATE.txt / HANDOFF G list them as running. The gate ran without their load.
- Q24 RESOLVED (the lead, 10-24): yes - E2 item (a) of the (not yet launched) ev script is 'the drop rule AND THE PLAN
  AS A TUBE' (events fixed at their frames, a per-frame x corridor shrunk by eps(k), steering inside it); the PROGRESS
  header line was written before the tube was added.
- Q25 THE SUITE'S SIZE: M3's own acceptance table sums to 279 move cases (112 / 111 / 56; P1-far-jcast 15, P1-jump 13);
  M4a's and M4b's tables give the same M3 v4 run as 275 (112 / 109 / 54; P1-far-jcast 13, P1-jump 11); T3 uses 279.
  Which count is right for the v4 reference?
- Q26 THE AIR DASH'S END ON THE LATTICE: the spec's open check 'the air sprint's eased fall clamp (-10 -> -30 u/s over
  1 s) may bite at the end of a long sprint' was not reported by any stage; T2 shows the bundle's ends equal for every
  A1_n of one step pattern, not that they lie on the A1 lattice. Is the dash's end on or off the lattice after a long
  sprint?
- Q27 RESOLVED (the lead, 10-24): the commit times are right (b3d9a8f 19:53 the ground dash as a bridge, bc452fa 19:56
  the ground dash back in the ground tables, both 10-23); the '20:05' / '20:15' in the notes were the lead's rough
  clock. The decision itself stands.

### 6.2 Known gaps in the models (not measured or not modelled)

- walls: kin_jit has the wall slide / cling / wall jump, the envelope engine and the tables have none (M1); the search
  keeps her off the walls with closed boxes; the use-time x clip misses the walls' vertical effects (T4); the Clawline
  block moves her through walls (T1 open 5); the roof polygons are Hang_04's (other rooms from their terrain).
- not offered by the envelope: the Clawline from the ground (the game allows it), the sprint's dash attack (not
  modelled, 3 trials), any attack in the ground dash / sprint (T4: `press.unmodelled` -> a forced collision).
- DOCUMENTED OVER-APPROXIMATIONS (each rejected by the final exact simulation when it lets a plan through): the lanes
  inside the float after a danger cut [M1]; short locks in a free-space table [spec]; CB_JH - jump held without a
  press - in an airtime's first frames [M1 finding 3; T4 keeps it documented, b2c9cf0]; the backward set inside the
  float's inertia (Back.exact) [T4]; the flattened layer outside Tables.valid_until [T4]; the x-only wall clip [T4];
  the lanes' hull after the Clawline's residual drift (T1 tightness: every miss over 0.1 u, 43 / 43, after a Clawline)
  [T1]; a window shape at a cluster's interval end (both facings, <= 2 run steps) [T2 open 4].
- no trial: an air dash -> landing -> air dash (H2_LAND_DASH from the decompiled code only); the far end of the hook's
  reach beyond ~8.6 u (live-probed to 10.2 u to the front; 4 of 89 airceil plans used it); the model's reach on a still
  Idle 11.75 vs 11.99 u (the reaction antic's body at the needle's hit).
- the Clawline's stop spreads wider than the strike module's two variants (near stops ~10 % under 1.1 u) [RFX]; the
  hook's stop inside one reflex cell shifts by a frame (the dash's 1.4 u steps).
- coarse in M2: the intro (Drop In at 48 u/s); the Clawline's hits (4 damage) react but push nothing.
- the entry case 0.032 u short (T2 open 2) and the engine's merge not monotone in its options (T2 open 7) - both chains
  equal the engine; a hidden field remains.
- the unexplained 1.5 % move starts not facing her and ~7 % of Idle's turns against the 0.5 s pause (M2).

### 6.3 Engineering items carried from the stages

- the split parts combine only their own contingent plans (a cross-part combination is lost) (M4b open 1).
- the variants' continuations are planned as if the variant were known at control; live it is known 2 f later at best
  (M4d open 3).
- the late check does not see an ACTION applied late by the oracle (S1 open 3); options for late ticks: plans robust to
  a key change a frame late, an ACTION carrying the next frame's keys, fewer skipped ticks (M4d2 open 2).
- two Clappers: map2 rarely in control (w13 2.5 - 7 %), the search's best within its cap mostly the noop / unsafe; the
  depth shares end a sliced decision early (M4b open 4).
- the commit check p99 20 - 25 ms with the press traces (S1 open 4).
- the reveal latency and map2's own CLAWSTRIKE (0 presses into a slam's first window).
- the supervisor judges with the fallback's plan while map2 has the keys (M4c open 6).

---------------------------------------------------------------------------------------------------------------------

## 7. Next steps (in the person's order; updated 2026-10-24 after the person's answers)

1. NOW (the ev workflow, offline): E0 profile; E1 the fast closed-loop evaluation - the escape funnel PER BEAM NODE (T4's
   proposal; the 44 funnel-only endpoints explained before any use), the danger per Clapper move / frame (Q9), the
   window shapes (3.6); E2 the handover - the drop rule with the plan as a tube (3.4.8), re-plan from mid-action, the
   fallback mid-swing, the unpredicted hook reaction, and THE BASELINE PLAN (Q2: map2 always provides a safe plan);
   every measurement with the tables ON (Q5) and the workers' memory watched; two verifiers; E3 fixes + a frozen
   checkout.
2. Wire the reflex's latency-gap types of the built table (claw_slam0, cast_claw, evade_claw) with the pre-reveal
   safety check on a worker; a live smoke (Q12).
3. The next w7 gate, no eye check (Q1): 16 / 16 hitless kills with map2 holding the keys >= 90 % (Q2 - the bar to
   confirm).
4. The long-term positioning planner (3.7).
5. The auto-generated routines replacing the reflex's hand-chosen window types (3.5).
6. The tables' state-recurrence fix and memory (Q5 - now that they are the main engine); the probes of section 6.2.
7. LATER, once map2 can replace the old controller (3.8) and positioning knowledge is needed (the person, 2026-10-24):
   the knowledge layer's recordings statistics with the clean-material rules (3.7).
