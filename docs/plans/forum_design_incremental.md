# Forum 连战的战斗栈设计（增量方案）

2026-10-03，分支 `design-forum-incremental`。依据：DESIGN §3.5（尤其 §3.5.3 支撑 / 概率、§3.5.4 规划器与预算、§3.5.6 Bind / 拼刀及 10-02 / 10-03 修订、§3.5.7 竞技场与你 10-03 关于多敌站位的几点）、§3.7.4（Q1 / Q1a / Q6 修订）；`docs/plans/M2.md`（Forum 打法、冲刺斩与飞针、降低风险的动作、危险区不变式、按键经济）；`docs/facts/1.0.30000/forum.md`、`movement_kinematics.md`、`m2_vision_view.md`、`probes.md`。

**角度：增量。** 保留现在的滚动视野规划器（候选 × 推演 × 字典序选择），只做解决问题所需的最小改动：预测里按敌人组合支撑；推演终点加终点价值（可逃空间 + 拟合的站位特征 + 机会价值）；新原语作为候选族；波次层写成剧本规则。每一项都写清楚改哪个文件、接口是什么、花多少算力。所有新代码只读视觉可得的信息（§3.8），开发和评估在 oracle 视图（M2.md 2026-10-03 你的决定）。

---

## 0. 一页摘要

**问题。** Bell Beast 门槛已过（oracle 98.6 %、模拟最终路径 94.4 %、0 WOULD_DIE），但整个战斗栈是单 Boss 的：一个 `BossTracker`、一个 `Forecast`、`boss_box` 一个打击目标、一维（地面 x）风险图。Forum 是 14 波、9 类敌人、同时最多 8 个活敌（两只 Maestro + 6 只小机械），中位 2–3 个；最后两只 Choir Clapper 当 Boss 打；有助战（Garmond、Cogfly）。M2 标准：≥ 70 % CLEAR、WOULD_DIE ≤ 1 %，然后 K1。规划器在一个 Boss 上就已超预算：今天同机实测 tick p50 7.2 / p99 20.2 ms（§1.2，负载下），DESIGN 目标 p99 3 ms。

**做法（六件事）：**
1. **多敌预测**：每个活敌一个 `EnemyTracker` + 现有的 walk（`Forecaster._walk/_place` 不变），模板按类型共享一个 `SupportQuery`；支撑取并集（逐点 OR），概率取 1 − Π(1 − pᵢ)（只用于打分）。对外接口与 `Forecast` 相同，规划器的 S / V / P 语义不变。确定路径的投射物（Throwing Bell、Reed 标枪、Clapper 炸弹列和 rune slam）用轨迹代替并集模板（Bell Beast 落铃的经验）。
2. **终点价值**：每个敌人一张"未来 0.7–2.0 s 的占据场"（粗栅格，10 Hz 轮转更新），推演终点在场上查三样：**可逃空间 E**（进字典序：在 V 之后新加一级"不被困"）；**拟合风险 r̂**（逻辑回归，特征含敌人间距 / 危险区重叠 / 夹击 / 墙角 / 下一波刷怪点，进 P 和 J）；**机会价值 O**（行为表的每招惩罚窗口 × 出招概率，含诱敌、分割、集火，只进 J）。硬安全仍只看支撑。
3. **新原语**：候选集按主角姿态分族（地面 / 墙 / 空中），加入冲刺、收割者冲刺斩、Clawline、贴墙 / 爬墙 / 墙砍、滑翔；每族 80–420 个候选，不再是一个 21 × 17 的全积。
4. **拼刀**：推演里的两个分支（成功：对方这一下作废 + 0.15 s 弹反无敌 + 取消后摇；失败：照常），风险 = 实测失败率 × 失败分支；按字典序自然只在 FORCED_RISK 时胜出，开不开由整场 A/B 决定（DESIGN §3.5.6 修订）。
5. **波次剧本（L3）**：`playbooks/Forum.yaml` 按波写先杀谁、开波前站哪、波间 Bind、Cogfly、终局左墙顶口袋的两条规则；视觉合法的波次跟踪器（数看得见的死亡和出场，不读 `room.battles`）。
6. **算力**：两段式检查（全部候选先跑标称一条线和中心点支撑查询，只有通过的前 K 个跑时序包络）、显式视野 48 → 36 帧（之后交给终点价值）、按姿态的候选族、敌人场轮转、命中效果只算前 64 行、截止时间的 anytime 选择。估计 Forum tick p50 ≈ 6 ms、p99 ≈ 12–14 ms（4 线程、训练负载）。**增量路线达不到 3–4 ms**；§4.6 请你决定预算口径。

**实施顺序**（§6）：F0 基线测量 → F1 多敌预测与支撑召回 → F2 多目标命中 → F3 新原语运动学 → F4 算力重构 → F5 终点价值 → F6 剧本与战术 → F7 拼刀 → F8 门槛与 K1（F9 可选：可反应分支放宽）。每步有离线验收，实战按波次课程（需要一个训练用 mod 命令跳到第 i 波，§5）。

**最大的风险**（§8）：Forum 行为表的支撑还不保守（留出核对 0.3–5.2 % 的接触在支撑 0.5 u 外，Bell Beast 是 0）；多个待机敌人的支撑并集让 FORCED_RISK 变多；算力。

---

## 1. 现状与测量

### 1.1 已有的东西（摘要，出处见各文件）

- **Bell Beast**：oracle 510 场 98.6 % CLEAR（11b4ca0）；模拟最终路径 degraded_dust 516 场 94.4 %（4a90331），0 WOULD_DIE，0 未预测命中；实战 tick p99 中位数 12.7 / 14.6 ms（probes.md）。
- **规划器**（`combat/planner.py`）：21 个首原语 × 17 个续接 = 357 个候选 + 上一帧计划 + Bind 宏；`kinematics.rollout(variants="bounds")` 9 条时序线的包络；S = 包络与支撑管道相交（`Forecast.occupied`，点查询膨胀模板）；命中效果（后坐、上砍停升、下劈弹起）重推演两次；锁定检查、尾部检查（`_tail_pick`：视野外 0.8 s 的 6 条退路）；字典序 `not Hz > not Hz_soft > not U > S=0 > 保持已承诺的跳 > comfort > V > min P > 最晚首次接触 > max J`。
- **预测**（`combat/forecast.py`）：`BossTracker` 一个 Boss；walk 按 Control 图放 `Placement`，`fastquery.query_par` 并行查询（包围盒剔除远处模板）；落铃 / 攻击铃有确定路径（`DetBell`）。
- **战术**（`combat/tactics/modes.py`）：HEAL / HEAL_SPOT / ENGAGE / PREPARE / EVADE / HOLD；风险图是地面 x 的一维覆盖率，同时是规划器 J 的终点项（`risk` 权重）。
- **Forum 知识**：14 波（forum.md §2）、9 类敌人的行为表（`knowledge/1.0.30000/enemies/forum/*.json`，`gauntlet_tables.GauntletBuilder`，13 场建表）；九类的 `support_conservative` 都是 false（留出 anchor 超出 0.5 u：Clapper 0.4 %、Clawmaiden 5.2 %、Minister 1.0 %、Maestro 0.6 %、Tiny 1.6 %、Reed 3.0 %、Envoy 0.6 %、Choristor 0.3 %、Bellbearer 0.9 %）；左墙顶口袋对 Clapper 的余量 ≥ 2.0 u，唯一漏洞是贴墙起跳（最近 0.87 u，forum.md §10.4）；Forum 运动学（贴墙、爬墙、蹬墙跳、滑翔、冲刺、Reaper 下劈、砍墙后坐、斜边）留出 99.26 %，其中 dash 97.34 %、glide 98.12 %，收割者冲刺斩和 Clawline 未建模（movement_kinematics.md §5）。
- **数据**：Forum 数据策略录像 122 场（`20261002_231917` 10、`20261003_014254` 25、`20261003_030413` 19、`20261003_074533` 33、`20261003_074719` 35）；行为表只用了其中 13 场。

### 1.2 今天的离线测量（同机，游戏实例和其他代理在跑，数字偏悲观；均为 below-normal 优先级）

**表 A：Bell Beast 规划器 tick 分解**（`ssbot.tools.planner_bench`，oracle 视图，录像 `20261003_144536_BellBeast_eval_planner_oracle/.../i4_000`（规划器自己的实战），7,951 tick，4 线程，ms）

| 阶段 | p50 | p99 | 说明 |
|---|---|---|---|
| 整个 tick（预测 + 战术 + 规划器） | 7.19 | 20.23 | 预测 + 战术 ≈ 0.65 / 3（= tick − planner total） |
| planner total | 6.55 | 17.16 | |
| filter（否决 + HoldFilter） | 0.45 | 1.44 | |
| rollout（bounds，约 358 × (P + 48)） | 3.07 | 4.84 | 47 % 的 p50 |
| support（含命中效果、锁定检查、comfort） | 2.24 | 10.73 | p99 的大头 |
| 其中 hit_fx（命中效果重推演） | 0.18 | 8.01 | 有攻击方案时才发生，p99 尖峰 |
| score / select / prob_bind / redirect | 0.15 / 0.15 / 0.04 / 0.00 | 2.91 / 2.35 / 0.86 / 2.69 | |

FORCED_RISK 1.65 % 的 tick；88 % 的 tick 选的是 CONTINUE（上一帧计划）。

**表 B：Forum 运动学推演**（`ssbot.tools.kin_bench_forum`，4 线程，200 次，ms，p50 / p99）

| 规模 | forum nominal | forum bounds | forum bounds_lo | hunter nominal | hunter bounds |
|---|---|---|---|---|---|
| 512 × 48 | 3.09 / 5.50 | 8.80 / 12.86 | 10.68 / 16.38 | 1.23 / 2.53 | 3.67 / 5.55 |
| 400 × 36 | 1.17 / 3.16 | 5.07 / 8.51 | 7.07 / 10.97 | 0.78 / 1.77 | 2.27 / 3.83 |
| 128 × 48 | 0.71 / 1.77 | 2.27 / 4.43 | 2.98 / 4.93 | 0.39 / 1.03 | 1.13 / 2.05 |
| 96 × 48 | 0.48 / 1.51 | 1.41 / 3.31 | 2.17 / 4.30 | 0.31 / 0.66 | 0.93 / 2.12 |

与 movement_kinematics.md §6 的记录一致（512 × 48：Forum bounds 8.34 / 12.20）。Forum 的规则（斜边、砍墙、相位机）让推演比 Hunter 贵 1.5–2.5 倍（规模越大差得越多）；bounds 比 nominal 贵 2.8–4.3 倍。

**表 C：每波同时在战的敌人**（数据策略录像 8 场 CLEAR，`20261002_231917` + `20261003_014254`，每 0.1 s 取样；"在战" = 该类 Control FSM 不在等待 / 休息状态；Clapper 的 Idle 被算作休息，所以第 7、13 波偏低；波 2 只持续约 1 s，并入波 3。脚本在会话临时目录 `forum_simul.py`，未提交）

| 波 | 设计敌人 | 平均在战 | 最多 | ≥ 3 个的时间占比 | 敌人间最小 \|Δx\| 中位 u | 最小 \|Δx\| < 3 u 占比 | 主角 6 u 内 ≥ 2 个 | 投射物平均 / p99 | 时长中位 s（随机策略） |
|---|---|---|---|---|---|---|---|---|---|
| 0 | Reed、Envoy、Choristor | 2.25 | 3 | 50 % | 2.44 | 57 % | 34 % | 0.28 / 1 | 44 |
| 1 | Choristor × 2（+4 s Garmond） | 1.69 | 2 | 0 | 5.10 | 33 % | 17 % | 0 / 0 | 28 |
| 2 + 3 | Bellbearer、Reed + Clawmaiden | 2.16 | 3 | 49 % | 2.34 | 59 % | 17 % | 0.96 / 3 | 52 |
| 4 | Minister × 2 | 1.99 | 2 | 0 | 6.13 | 28 % | 19 % | 0.01 / 1 | 28 |
| 5 | Clawmaiden（+ 波 4 剩 1 只） | 1.30 | 2 | 0 | 5.93 | 30 % | 6 % | 0.09 / 1 | 47 |
| 6 | Maestro × 2 + Tiny ≤ 6 | 5.32 | 8 | 97 % | 0.63 | 94 % | 22 % | 0 / 0 | 207 |
| 7 | Clapper | ≥ 0.76 | 1 | — | — | — | 0 | 1.72 / 10 | 59 |
| 8 | Reed × 2、Bellbearer | 2.11 | 3 | 52 % | 2.25 | 61 % | 20 % | 1.12 / 3 | 55 |
| 9 | Choristor、Bellbearer × 2 | 2.95 | 3 | 97 % | 1.49 | 70 % | 22 % | 1.28 / 2 | 17 |
| 10 | Clawmaiden（+ 波 9 剩 2） | 1.90 | 3 | 29 % | 2.17 | 60 % | 14 % | 0.97 / 3 | 34 |
| 11 | Bellbearer、Minister × 2 | 2.26 | 3 | 56 % | 2.22 | 61 % | 18 % | 0.68 / 2 | 61 |
| 12 | Maestro、Reed + Tiny ≤ 3 | 4.08 | 5 | 95 % | 0.72 | 92 % | 26 % | 0.19 / 2 | 69 |
| 13 | Clapper × 2 | ≥ 1.34 | 2 | 0 | 3.12 | 48 % | 2 % | 2.44 / 12 | 154 |

全程（按时间）：≥ 3 个在战 47 %、≥ 4 个 26 %、≥ 6 个 10 %（随机策略下 Maestro 波拖得长，这些占比偏高）。最常见的组合：Maestro + 3 Tiny、两只 Clapper、两只 Maestro + 6 Tiny、Bellbearer + 2 Minister。

### 1.3 由此得到的设计约束

1. **K（在战敌人数）的典型值 2–3，最坏 8**；Tiny 总是挤在 Maestro 周围（最小间距中位 0.6 u），包围盒剔除会把它们当成一团处理，查询代价按"空间上分开的团数"增长，不按敌人数。
2. **敌人大多不在主角身边**（6 u 内同时 ≥ 2 个：多数波次 14–26 %，最高第 0 波 34 %，Clapper 波 0–2 %），这和你"高庭的怪会控制距离"一致：近身靠冲刺斩 / Clawline，所以新原语不是锦上添花。
3. **推演是第一大成本**，Forum 运动学又贵 2.5 倍；不改结构的话，光 400 × 48 bounds 就 ≈ 7 / 10 ms。**两段式检查是必须的**（§4.2）。
4. **p99 来自偶发的重计算**（命中效果、重定向），所以"每 tick 一定做"的工作和"偶尔做"的工作都要设上限。
5. **投射物多**（终局 p99 12 个：Bomb Cast 9 对炸弹），并且大多路径确定：用轨迹不用并集。

---

## 2. 增量原则：不变的与要改的

**不变：** 每帧重规划；候选 × 推演 × 字典序；支撑决定 S、概率只用于 P / J；HoldFilter 和按住时序在按下时承诺；锁定检查、尾部检查、Bind 宏、ABORT；安全过滤器（Forum 场内无危险物：TERRAIN hazards 0）；监督器的结构和 Q 规则；永不学习的部分（DESIGN §3.5.8）。

**改：**
- 预测从"一个 Boss"变成"一组敌人的并集"（§3.1）。
- 打击目标从一个变成 K 个，加集火权重（§3.2）。
- 候选集按姿态分族，加新原语（§3.3）。
- 视野外：在 V 之后加一级"不被困"，J 加终点价值三项（§3.4）。新的字典序：

```
not Hz > not Hz_soft > not U > S=0 > 保持已承诺的跳 > comfort > V > not trapped > min P' > 最晚首次接触 > max J'
    P' = P + λ·r̂(end)                     （只在 FORCED_RISK 时比较）
    J' = J_hits(Σ_k w_k·h_k) + J_other + w_E·E(end) − w_r·r̂(end) + w_O·O(end)
```

  "not trapped"放在 V 之后、P 之前：它不是安全（不看支撑之外的东西不能当安全），但比"打得多"重要。这一级取代现在 `_tail_pick` 的大部分作用（`_tail_pick` 保留，对最终选中的计划做一次精确的视野外退路检查）。
- L3 剧本加波次（§3.6），L2 战术加多敌模式。
- 预算机制：截止时间与 anytime 选择（§4.4）。

---

## 3. 架构：改哪里、接口是什么

### 3.0 改动清单

| 文件 | 改动 | 新 / 改 |
|---|---|---|
| `combat/enemy_tracker.py` | `EnemyTracker(model, view)`：单个敌人实例的状态与入口时间、锚点、死亡尾巴；`roots(origin_t) -> (list[Root], known)`，与 `BossTracker.roots` 同形 | 新 |
| `combat/forecast.py` | `Forecaster(model, view, tracker=None, query=None, query_c=None)`：可注入通用跟踪器和共享的 `SupportQuery`（默认行为不变，Bell Beast 逐位相同）；walk 结果按 (状态, 入口时间格) 缓存 | 改（小） |
| `combat/multi_forecast.py` | `MultiForecaster` / `MultiForecast`（§3.1） | 新 |
| `combat/projectiles.py` | Throwing Bell（复用 `pogo_targets` 注册表 + `DetBell` 机制，含钉子改向）、Reed 标枪（直线、插墙）、Clapper 炸弹列与 rune slam 的确定路径 | 新 |
| `combat/terminal.py` | 敌人占据场、可达模板、E / r̂ / O 的 numba 核（§3.4） | 新 |
| `combat/planner.py` | K 个目标的 `_score_kernel` / `_first_hits` / `_hit_effects`；拼刀分支；两段式检查；`trapped` 一级；截止时间；`PlannerConfig` 新字段 | 改 |
| `combat/candidates.py` | `build_ground / build_wall / build_air(T, abilities)`；新 `Piece`；`pocket_macro` | 改 |
| `knowledge/kin_jit.py`、`kinematics.py` | `M_DASH_STAB`（收割者冲刺斩）、`M_HARPOON`（Clawline）；贴墙地面冲刺穿墙、Sprint Grace 计时两个已知错误 | 改 |
| `knowledge/gauntlet_tables.py`、`tools/behaviour_build.py` | 另出：每类受击框平均路径表（box tables）、每招惩罚窗口表、"待机到最快一击"统计、可拼刀碰撞体分层模板、死亡帧身体尾巴 | 改 |
| `combat/tactics/gauntlet.py` | `GauntletTactics`：多敌模式、目标选择、二维风险 / 机会图、剧本执行 | 新 |
| `combat/tactics/playbook.py` | 波次 schema | 改 |
| `knowledge/1.0.30000/playbooks/Forum.yaml` | 波次剧本 | 新 |
| `combat/wave_tracker.py` | 视觉合法的波次跟踪（§3.6.3） | 新 |
| `safety/supervisor.py` | 按实例、按家族伤害的支撑事件；多段链的 D；YELLOW 下的击杀冻结；口袋作为 Q1a 安全点只在终局 | 改（小） |
| `train/planner_policy.py` | `enemy="Forum"` 路径；统计（每波受击、敌人在长招里的占比、按键经济） | 改 |
| `backends/observability.py` | Forum 类型的可见性规则（位置、框、朝向；不传 hp、不传 FSM） | 改 |
| 工具 | `support_recall --encounter Forum`、`planner_bench --encounter Forum`（数据录像开环）、`risk_fit`、`punish_tables`、`opportunity_audit` 的 Forum 版、`fight_stats` 的 Forum 节 | 新 / 改 |

### 3.1 多敌预测（`multi_forecast.py`）

**对象。**
- **subject**：一个在战敌人（HealthManager 根实体；视觉侧是一条检测轨迹）。`MultiForecaster.update(ws)` 维护 `subjects: dict[track_id, Forecaster]`：新出现的敌人建一个（共享该类的 `BossModel` 和 `SupportQuery`），死亡后保留 `DEATH_TAIL` 帧（forum.md §11：19 次支撑外接触里 5 次是"被打死那一帧的身体"，终局 Clapper 死后十几帧本体仍伤人；表里统计每类死后身体还开着的最长帧数，作为该类的死亡尾巴模板）。
- **等待中的下一波**：波次跟踪器给出"下一波最早 / 最晚开始时间"（§3.6.3）时，按波次表的出生点放该类的 ENTRY 家族模板（`<P>_ENTRY`，锚在出生点）。入场家族每场只有 1–5 个实例，到 200 要 6–13 h（forum.md §11）；入场是脚本化的（固定出生点、固定 FSM 路径），所以先用"所有记录过的入场 + 状态机上可能的分支"的并集，加大余量，不等 200。
- **投射物**：所属招的模板（表里已按 4 s 窗口归给招）仍是默认；能确定路径的换成轨迹（`projectiles.py`）：
  - Throwing Bell：重力 1.0、弹墙 / 弹地 / 弹顶、被钉子打中 Tink L/R/U 改向（forum.md §9.2 FSM）：与 Bell Beast 落铃同一套（`pogo_targets` 注册表 + `DetBell`），打铃改向进入"降低风险的动作"（§3.2）。
  - Reed 标枪：直线飞行，插墙后碰撞体关闭；可拼刀（parry 5）。
  - Clapper Bomb Cast：`First Bomb` 后 9 对、每 0.15 s 一对、间距 4.2、y 3.67、r 2.17（forum.md §10.1）：施法位置一定，整列确定。
  - rune slam：Jump Cast 落地约 2 s 后在落点出现，再 1.28 s 爆，r 7.19、中心 y ≈ 3.34：落点确定后就是一个定时圆。
  这些确定路径比并集小得多（Bell Beast：攻击铃上精确路径后 Burst Recovery 的 FORCED 57.7 % → 9.6 %，m2_vision_view.md 第二轮 §2）。

**接口（与 `Forecast` 同名同义，规划器不需要知道有几个敌人）：**

```python
class MultiForecast:
    subjects: list[Subject]                      # id, type_key, Forecast, alive, hp_est, committed(bool)
    def occupied(self, x, y, tk, comfort=False) -> np.ndarray      # [N, T] 并集（OR）
    def occupied_without(self, x, y, tk, exclude) -> np.ndarray    # exclude: subject id 或投射物 type key
    def prob(self, x, y, tk) -> np.ndarray                         # [N] 1 - Π(1 - p_i)，只用于打分
    def t_min(self, x, y, t_max=3.0, subject=None) -> float        # 并集或单个敌人
    def committed(self) -> "MultiForecast"                         # 各敌人的 committed() 的并集
    def support_set(self, ws=None, t1=0.8) -> SupportSet           # 每个实例一个事件，伤害按家族
    def targets(self, tk) -> list[Target]                          # 每个活敌的受击框路径 + 投射物目标（§3.2）
    def fields(self) -> EnemyFields                                # §3.4 的占据场（上一次轮转的结果）
```

**组合规则。** 支撑：逐点 OR（每个敌人的支撑是保守的，并集仍保守）。概率：假设各敌人独立，P = 1 − Π(1 − pᵢ)（只进 P / J，不碰 S）。`support_set`：每个 subject 一个 `SupportEvent`（instance = track id），伤害取该敌人支撑中各家族的最大值（Clapper 2、Clawmaiden Spear / 矛爆炸 2、rune slam 2，其余 1）；多段攻击链（Choristor Whip、Reed ParrySlash、Minister Slash Collider：`multi_wounder`，连上后由 `hornet_multi_wounder` 继续扣血）按整链伤害计（导出 eff 2）；`hits_to_death` 的 D1 = 支撑中最大事件伤害，规则不变。

**查询的组织。** 每种在场的类型一次 `query_par`（该类所有 subject 的 placement 放进同一个 `SupportQuery`），结果 OR。不把 9 类模板合成一个大 `SupportQuery`：Bell Beast 一类打包后约 0.2–0.3 GB（forecast.py 注释），9 类全合起来乘 4 个实例内存不可接受；按类型分开还可以**按波懒加载**：当前波 + 下一波的类型常驻，其余在波间（P1 登记的安全窗口）加载 / 释放。每类的模板体积在 F1 实测（npz 目前未提交，要用 `behaviour_build` 重建）。

**walk 缓存。** 一个敌人的 walk 只依赖（当前状态、入口时间、ctx）；状态不变时，上一 tick 的 placement 列表整体平移 1/60 s 就是这一 tick 的结果（placement 的时间是相对原点的）。所以只在 subject 进入新状态、新出现或死亡时重走；Bell Beast 的预测 + 战术今天 p50 ≈ 0.65 ms，按 K = 3 且多数 tick 命中缓存，估计 p50 ≈ 0.6 ms、p99 ≈ 2 ms。

**保守性门槛。** 九类表现在都不保守。F1 先用全部 122 场重建（现在只用了 13 场），再测留出召回；在 `support_conservative` 为真之前，每类在 planner 里加 `margin_type`（留出残差 p99.9，按类型），并在 `MultiForecast` 上标 `known=False` 的类型让监督器知道支撑没认证。

### 3.2 多目标命中、集火与"降低风险的动作"

**目标。** `MultiForecast.targets(tk)`：每个活敌一份受击框沿它当前家族平均路径的预测（`box_tables` 按类型重建；Bell Beast 的 `boss_box` 就是 K = 1 的特例）+ 多边形；投射物目标（Throwing Bell：侧砍改向、下劈弹起；Reed 标枪：拼刀弹开）。

**打分。** `_score_kernel` 改成 K 个目标：`boss [K, T1, 4]`、`okb [K, T1]`、多边形按目标拼接带 `starts`；每个目标各自计 `h_k`，`J_hits = Σ_k w_k · min(h_k, cap_k)`。代价随 K 线性增加，但先按"候选包围盒 ∩ 目标路径包围盒"剔除（远处的敌人一行都不算），典型 K_eff ≤ 3。

**集火权重** `w_k = w_hit · kill_k · focus_k · prior_k`：
- `kill_k`（击杀价值）= 去掉 k 之后主角周围占据场缩小的量 ÷ 打死 k 还需几刀（HP 估计 / 每刀伤害）。占据场是 §3.4 的 per-enemy 场，"去掉 k" 是 leave-one-out 的 OR，所以这一项几乎不花额外算力。这正是你说的"击杀永久移除一份威胁，价值按它让危险区缩小的量算"。
- `focus_k`（各个击破）：除 k 以外的所有敌人对主角所在区域的 `t_min` 都 > `T_focus`（1.0 s，可调）时乘 (1 + β)：别的怪够不着，就盯着这一个打。
- `prior_k`：剧本的类型优先级（先杀 Clawmaiden；其次远程：Bellbearer、Reed、召唤者 Maestro；再近战；Clapper 最后）。DESIGN §3.5.5 的群战顺序变成权重而不是硬规则，A/B 可调。

**命中效果。** `_hit_effects` 本来就循环目标列表：加入所有敌人后，砍中任何一个都会后坐（Reaper 3.75 u/s × 8 步）、上砍停升、下劈弹起（下劈对敌人的弹起与 i-frame 照旧）。新增三种：
- **击杀**：HP 估计 ≤ 本刀伤害的命中，在命中分支里该 subject 的支撑在 `DEATH_TAIL` 之后移除（`occupied_without`）。规划器因此会把"打死它"看成更安全，而不是单纯的输出。
- **防御姿态的反击**：Minister `MI_PARRY`（Parry Stance → ParrySlash Hit 1–4）、Reed `RE_DEFEND`：攻击碰到处于这些状态的受击框 → 命中分支加上反击模板（行为表里记录过的反击实例），按 S 判。剧本里再写一条"防御姿态时不近战"（同 DESIGN §3.5.5 Lace 2）作双保险。
- **打 Throwing Bell**：改向规则复用 Bell Beast 的 `pogo_targets.tink`（侧砍按朝向改向、下劈截 vy），属性测试同 `bell_hit_audit`："打铃之后主角周围的危险区不得大于不打"（M2.md 一致性原则），推广到击杀和拼刀弹开投射物。

**上限。** 命中效果的重推演只对 J 排名前 64 的有命中行做（今天 p99 8 ms 的尖峰就在这里）；超出的行保留"未命中分支"的 S（保守）。

### 3.3 新原语与按姿态的候选集（`candidates.py`）

**原语和运动学状态：**

| 原语 | 运动学 | 状态 | 先做什么 |
|---|---|---|---|
| DASH（地面 / 空中，L/R） | `M_DASH` → `M_SPRINT` | 留出 97.34 %：贴墙地面冲刺被模型推进墙里；Sprint Grace 计时起点两份录像矛盾 | 修这两处（movement_kinematics §1.3、§5.3） |
| DASH_STAB（收割者冲刺斩） | 无 | Sprint FSM Reaper Antic / Upper / End：Upper 向前 50 u/s、每步 ×0.85、0.3 s 的 vy 曲线，End vy 7（movement_kinematics §5.4）；多边形 `Attacks/Scythe/DashUpper Slash` 要部署 `slash.dump paths` 后采 20–40 次 | 新 `M_DASH_STAB` |
| CLAWLINE | 无 | 反编译 Clawline（harpoon）相关 FSM，量飞行速度、命中判定、拉近终点、失败分支【未核实】；需要可钩目标（敌人）在射程内 | 新 `M_HARPOON` |
| 贴墙 / 滑墙 / 蹬墙跳 / 墙砍 / 上砍下砍离墙 | 有 | wall 100 % | — |
| 爬墙（Scramble，滑墙中按朝墙 + 冲刺） | 有 | 99.48 % | — |
| 滑翔 | 有 | 98.12 % | — |
| Reaper 下劈 | 有 | 99.94 % | — |
| TOOL（Cogfly，Red / Up 槽，4 次） | 只有出手硬直 | 量投掷硬直和对主角运动的影响 | 剧本宏（§3.6） |
| BIND | 有 | — | 宏照旧 |

**按姿态分族**（每 tick 按起始状态的姿态选一族；首原语只在该姿态下有意义）：

| 族 | 首原语（估计个数） | 续接（估计个数） | 候选 |
|---|---|---|---|
| GROUND（站地） | WAIT、MOVE × 2、JUMP(11/24/48) × 3 方向、ATTACK 侧 × 3 / 上 × 2 / 下 × 2、SILKSKILL × 2、DASH × 2、DASH_STAB × 2、CLAWLINE × 0–2（只在有目标进射程时） | 现有 17 个按 Forum 录像里的使用率修剪，加"冲刺回撤""跑向墙 → 起跳 → 贴墙" | 25–27 × 16 ≈ 400–430 |
| WALL（滑墙 / 贴墙） | HOLD（贴住）、SLIDE（松开）、WALLJUMP(11/24) × 背墙、SCRAMBLE、WALL_SLASH、UP、DOWN 离墙、DASH 离墙、GLIDE 离墙 | 8（贴住、贴住 + 第 t 帧墙砍、回墙、落地、滑走、再爬…） | 10 × 8 = 80 |
| AIR（空中） | 漂移 N / L / R、ATTACK 侧 / 上 / 下（带方向）、空中 DASH × 2、GLIDE、松跳 | 12 | 12 × 12 = 144 |

`Prim` 增加 DASH_STAB、CLAWLINE、CLING、SCRAMBLE、GLIDE、TOOL；监督器的允许表：DASH / CLING / SCRAMBLE / GLIDE 属于躲避性移动（PAUSE_PENDING 也允许，I2 照常），DASH_STAB / CLAWLINE 属于攻击（会触发冻结：PAUSE_PENDING 禁止），TOOL 同工具。

**宏。** `pocket_macro`：跑到左墙 → 起跳 → 贴墙 → 爬到口袋（pos y 13.45–13.60），作为一个宏候选（像下劈宏一样：开始后保持，除非别的计划高出 `MACRO_MARGIN`），安全检查照常走推演。数据策略的爬墙很少成功（5,621 帧贴墙里只有 145 帧在 y ≥ 13.3，forum.md §10），宏要用运动学的蹬墙跳 / 爬墙模型写，离线在 `kn_forum_wall` 上验证成功率。

**为什么不做全积。** 全积 = 首原语 × 续接，GROUND 27 × 17 = 459 就已经接近 512 的推演上限，而且 Forum 的推演贵 2.5 倍；按姿态分族后墙上和空中的 tick 便宜得多（80 / 144），平均 N 下降。

### 3.4 终点价值（`terminal.py`）

**占据场。** 对每个 subject i，在粗栅格上算它未来的支撑占据：x 14.0–49.0 步长 0.5 u（70 列）、y 3.5–17.5 步长 1.0 u（15 行），共 1,050 格；时间 t_j = 0.7–2.0 s（相对当前帧）每 0.1 s 一格，14 格；即每个敌人 14.7k 个点查询。结果 `F_i[cell, j]` 存位图。并集 U = OR_i F_i，计数 C = Σ_i F_i。
- **轮转更新**：每 tick 只重算一个敌人的场（轮流），某个敌人进入新攻击（walk 的根变了）或新出现时立即重算它。场只用于打分，过期 ≤ K 帧不影响安全。一个敌人的查询与一次 `_contacts`（约 19k 点）同量级，估计 0.3–0.5 ms。
- 这张场同时给出：risk 图（二维，取代战术里的一维地面风险图）、leave-one-out 的击杀价值（§3.2）、危险区重叠（C ≥ 2 的格子）。

**可逃空间 E（DESIGN §3.5.7 第 1 层）。**
- **可达模板**（离线）：按终点姿态分类（站地静止 / 向左跑 / 向右跑、空中上升 / 下降按 vy 分 3 档、贴左墙 / 贴右墙），用运动学推演一组原语库（跑、跳、冲刺、蹬墙跳、滑翔、落下），记录 0.2 / 0.5 / 0.9 / 1.4 s 时可达的格子偏移（取并集），再按场地内部掩膜裁剪（Forum 场内没有平台：地面 y 3、墙 x 14.01 / 48.99、穹顶，forum.md §8.1）。
- **E(end)** = Σ_j w_j · |R_j \ U_j| / |R_j|，w_j = 1 / (1 + t_j)，R_j 是终点状态在 t_j 的可达格子（时间格对齐到最近的场时间格）。
- **trapped(end)** = 存在某个 t_j ≤ 1.4 s 使 R_j ⊆ U_j（所有可达格子都被占），即"现在每个怪都躲得开，几秒后两边都有怪、没有退路"。被夹击、退到死角、站在下一波刷怪点上都会让 E 变小、trapped 变真，不用写规则。
- 只对两段式检查后剩下的前 K_b 行算（§4.2），K_b = 96–128，每行约 4 个时间格 × 每格 ≤ 150 个偏移，numba 并行估计 ≤ 0.1 ms。

**拟合的站位风险 r̂（DESIGN §3.5.7 第 2 层）。**
- 特征 φ(end)：
  1. 每个敌人 `d_i / r_fast(type_i)`：主角到它的距离除以该类"从待机到最快一击"的触发距离（行为表统计，按距离分档检验过的才用）；取最小值和次小值；
  2. 危险区重叠：R ∩ (C ≥ 2) 的占比（你的纠正：判据不是"同侧 / 两侧"，是危险区和危险时段是否叠在一起）；
  3. 夹击：主角左右 8 u 内都有敌人；
  4. 场地位置：到最近墙 / 墙角的距离；到"下一波 3 s 内可能开始"时的出生点的距离；左墙顶口袋只在终局类型集里作为例外（单独一个指示特征）；
  5. 在战敌人数、在长招里的敌人数、在待机的敌人数（你的补充：不出招的怪才危险）；
  6. 主角姿态（地 / 墙 / 空）、风险档。
- 模型：逻辑回归（L2），标签 = "接下来 2 s 内主角被打中"（damage 事件 + LethalBlock 拦下的致命伤）。先在 122 场数据策略录像上拟合（每场约 200 次受击，正样本充足），按场分折留出；规划器上线后在它自己的录像上重拟（分布不同：规划器躲支撑，剩下的风险是支撑之外的东西）。验收：留出 AUC、校准误差（M2.md"预测必须可检验"）。
- 用法：J 里 −w_r·r̂；FORCED_RISK 时 P' = P + λ·r̂ 做次级排序。**从不进 S。**

**机会价值 O（DESIGN §3.5.7 第 4、5 层：每招的破绽、诱敌、分割、各个击破）。**
- **惩罚窗口表**（离线，`punish_tables`，推广 Bell Beast 的 `safe_windows`）：对每类每个家族 a，按主角相对敌人的偏移 (dx, dy)（0.5 u 格，按朝向镜像）统计"这一招从开始到结束，主角整套'出刀 + 后摇'（Reaper：攻击 0.35 s、硬直 0.3 s，movement_kinematics §3）完全落在这招支撑之外、且刀的多边形够得着受击框"的秒数 `Pun_a[dx, dy]`，以及窗口开始的时间。所有招都算（不只长招）。
- **待机的先手**：每类"从待机到最快一击"的时间和距离分布（行为表）；主角的"出刀 + 后摇"短于它时才能先出手——这一条支撑检查已经覆盖（锁定检查覆盖整个后摇），O 里不重复。
- 运行时：
  - 敌人 i 已经锁在招 a 里（committed）：O_i = Pun_a[终点相对 i 的偏移] × 剩余比例；
  - 敌人 i 在决策状态：O_i = Σ_a p_i(a | 距离档, 高度档, 主角状态) × Pun_a[偏移] × γ^(到决策的时间)，p 来自行为表的条件转移（Clapper 的 Slam Range、Choristor / Minister 的距离依赖，forum.md §11）——**诱敌**就是让 p(长且可惩罚的招) × 窗口变大的位置，自动从这一项出来。
  - **分割**：O_i 乘 solo_i = 1 − (i 的惩罚格子里被其他敌人场占据的比例)。两只怪聚在一起时彼此的惩罚格子被对方的危险区盖住，solo 小；"左右各一个、各自在长招里左打一下右打一下"的局面 solo 大。
  - 总 O = Σ_i w_i · O_i（w_i 同 §3.2 的击杀价值）。
- 只进 J；怪不按概率出招时，计划在支撑下照样安全（DESIGN §3.5.7 第 5 层）。

**自适应视野。** 敌人锁进已知时长的长招时，`long_horizon` 照旧把视野延到招式结束（现有机制，按每个敌人取最大），这样"放完 A 的长招去打 B"能被规划出来。

### 3.5 拼刀：降低风险的动作（DESIGN §3.5.6 修订）

- **可拼刀表**（静态知识，离线）：oracle 导出的 parry 位（5 = clash + counter）给出每类哪些碰撞体可拼：Choristor `Slash Hit 1–3 / Spin Hit / Spin Slash Hit`、Reed `Stab Hit 1–3` 与标枪、Envoy `Charge / P1 / P2 / JumpSlash Damager`、Maestro `Slash Hit 1/2`、Clawmaiden `Slash Collider 1–4`、Minister `ParrySlash Hit 1–4`（forum.md §9.2）；本体框（1/4）不可拼。模板按碰撞体分层：可拼层 / 不可拼层（`behaviour_build` 输出两份 key）。
- **推演**：在命中效果那一步，若某候选的刀在有效帧内碰到某个敌人已承诺招的可拼层，就生成两个分支：
  - 成功：从拼刀帧起，这次攻击实例的模板不再计（投射物改为弹开后的路径）；主角 0.15 s 弹反无敌 + 冻结 + 取消后摇（`NailParryRecover`：攻击持续、冷却全部清零，M2.md）→ 推演事件 `EV_CLASH`；
  - 失败：原样（可能接触）。
  S(c) = 失败分支的 S；P(c) = p_fail × 失败分支的接触概率。于是：有完全安全的方案时选安全的（钢魂）；全都有风险时拼刀可以凭更低的 P 胜出；失败也安全的拼刀按收益正常比较。
- **成功率**：按（类型、招、视图）实测：数据策略加"定时对着可拼招出刀"的段，oracle 的冻结事件和 `NAIL CLASH` 标记成败；n < 30 时用保守先验 0.5。
- **白名单**照旧：日志里观测到过拼刀；YELLOW 和 PAUSE_PENDING 禁用（拼刀冻结会吞暂停）；失败不靠面具也能活（HP − D ≥ 2）。
- **整场 A/B**：拼刀开 / 关（按类型 × 招的组），每组 ≥ 200 个随机起点（波次课程，§7），比每波受击、WOULD_DIE 上界、退出数和用时；结论写进剧本（DESIGN §3.5.6"整场风险而不是每一帧"）。
- 算力：只多出"刀碰到可拼层"的那些行的一份推演，上限 16 行。

### 3.6 波次剧本（L3）与多敌战术（L2）

#### 3.6.1 `playbooks/Forum.yaml`（schema 示例）

```yaml
encounter: Forum
loadout_arms: [fo_A, fo_B, fo_C, fo_A5]          # Reaper+Grip+助战 / Hunter_v2+助战 / 无助战 / 5 面具
priority: {Song Handmaiden: 3.0, Pilgrim 03 Song: 1.6, Song Reed: 1.5, Song Pilgrim Maestro: 1.5,
           Song Pilgrim 01: 1.2, Song Pilgrim 03: 1.0, Song Administrator: 1.0, Song Automaton Tiny: 0.6,
           Song Heavy Sentry: 1.0}             # §3.2 prior_k，A/B 可调
forbid:
  - {enemy: Song Administrator, state: [Parry Stance Antic, Parry Stance], do: [no_melee]}
  - {enemy: Song Reed, state: [Defend Start, Defend], do: [no_melee]}
waves:
  - {index: 0, note: "开场由吼叫过场接管，起点约 x 33.0；Reed 从 (30.73, 12.53) 下来，Choristor 在 (19.41, 4.53)"}
  - {index: 1, garmond_at_s: 4.0}
  - {index: 3, pre_stance: {avoid_spawn: [[1.67, 46.23]], why: "Clawmaiden 从左上远处飞进"}, kill_first: Song Handmaiden}
  - {index: 6, cogfly: 2, kill_first: Song Pilgrim Maestro}      # Tiny 是对象池，Maestro 不死会再召
  - {index: 7, pre_stance: {avoid_x: [[27.0, 35.0]], why: "Clapper 从 (31.03, 25.73) 落下"}}
  - {index: 13, pre_stance: {avoid_x: [[17.0, 25.0], [38.0, 46.0]]}, mode: POCKET, cogfly: 2,
     pocket: {x: 14.27, y: [13.45, 13.60], climb_veto: "Clapper 本体左沿 <= 14.6",
              threat: "面朝左且 pos x <= 18 的 Clapper"}}
inter_wave_bind: true                             # Bind 提交测试按出场模板自动判断（§3.6.2）
```

这些条目的内容来自 forum.md 的波次表、出生点和口袋分析；`priority` 和 `cogfly` 的分配是起点，靠 A/B 定。

#### 3.6.2 规则的含义

- **先杀谁**：不是硬顺序，是 §3.2 的 `prior_k`（乘在击杀价值上）；Clawmaiden 偷丝（Silk Suck），所以优先级最高（DESIGN §3.5.5）。
- **开波前站哪**：波次跟踪器说"下一波可能在 [lo, hi] 开始"时，出场模板进支撑（§3.1），可逃空间 E 自然避开刷怪点和落点；`pre_stance` 只是战术层的 stance 拉力。
- **波间 Bind**：Bind 提交测试（`bind_allowed`：丝 ≥ 9、T_min ≥ 1.37 + 0.15 s）里的 T_min 用并集支撑加出场模板算。startDelay 0.5–3 s 加入场动画（入场家族的停留时间）通常给出窗口；测不过就不 Bind。Q1a 的"去安全点 Bind"只在终局（只剩 Clapper）用口袋：其他波次口袋不安全（Reed 本体、Tiny、Minister、矛爆炸都到过口袋，0.00 u，forum.md §10.3）。
- **Cogfly**：4 次；默认第 6 波 2 次、终局 2 次（第 6 波在随机策略下是最长的一段，中位 207 s）；作为剧本宏在指定波的开头放出（出手硬直要过支撑检查），A/B 比较"第 6 波 / 终局"与"按需"。
- **终局口袋**（你的打法 + forum.md §10.4 的两条规则）：模式 POCKET 时 stance = 左墙顶；`climb_veto`：Clapper 本体左沿 ≤ 14.6 时不上去；人在口袋里时面朝左、pos ≤ 18 的 Clapper 按威胁处理（它这时起跳，本体会擦到口袋 1 u 以内）。这两条本应由 CC_JUMP / CC_JUMP_CAST 的支撑自动得到（前提是表覆盖了少见的近墙起跳），剧本里写成额外的否决作双保险。贴墙时墙砍够得着跳到高处的 Clapper 至少一半（左沿 ≤ 18.6，forum.md §10.4），由打分逐次判断；地面安全时下去打，由字典序自动决定。
- **Garmond**：他的攻击永远不算威胁（他在 Forum 里伤主角的碰撞体不启用，forum.md §4）；Clapper 的伤害大头来自他（3 个运行里 Garmond 270 次命中对 Hornet 106 次）。先不写规则；数据里检验"敌人被 Garmond 缠住时的出招分布"是否不同，显著就作为行为表的条件变量。

#### 3.6.3 视觉合法的波次跟踪（`wave_tracker.py`）

- 输入：静态波次表（场景包，离线知识，合法）+ 看得见的事件：敌人死亡（死亡动画 / 消失）、新敌人出现、助战出现。
- 规则（反编译 `BattleScene`）：当前波活着的数量 ≤ `remainingEnemyToEnd` 时下一波在 `startDelay` 后开始；开波 1 s 后按子物体数再检查一次（波 2 并入波 3 就是这条）。输出：当前波索引、下一波开始时间区间、出生点。
- oracle 视图里用 `GauntletTap`（`room.battles`）作为**测试真值**比对，不作为输入。

#### 3.6.4 L2 多敌战术（`tactics/gauntlet.py`）

模式：HEAL / HEAL_SPOT（Q1a，同现在）、ENGAGE(i)（目标 i 在惩罚窗口里）、BAIT(i)（站到 O_i 最大的距离带）、SPLIT（两个敌人危险区重叠大时站到让它们分开的一侧）、EVADE、HOLD、PRE_WAVE、POCKET。每 10 Hz 和事件时重选：目标 = argmax_i w_i · O_i（§3.2、§3.4），stance = 目标附近 O 场最大且 E 不低的格子；模式只给 stance 和权重，安全由规划器的字典序保证。

### 3.7 监督器（小改）

- `support_set` 来自 `MultiForecast`：每个实例一个事件，按家族伤害；D1 = 最大事件伤害（Forum 多数时间 D1 = 2：Clapper、Clawmaiden 矛、rune slam、多段链）。7 面具时：HP 7 → h = 4，HP 5–6 → h = 3（GREEN），HP 3–4 → h = 2（Q1a 先回血；Q6 新规则：h = 2 时不因 FORCED_RISK 退出，攒丝），HP ≤ 2 → h = 1（Q1：受击无敌窗口里退出）。
- 多段链（`multi_wounder`）是否绕过面具【未核实】：在核实前按"整链伤害、面具覆盖"处理；若不覆盖，列入 Q3。
- **击杀冻结**：YELLOW 档"不打可能致死的一击"（击杀冻结吞暂停）要每个敌人的 HP 估计：视觉合法的做法是数看得见的命中（`hp_est − 3σ ≤ 本刀伤害` 就算可能致死）；每类击杀冻结时长离线实测。Forum 一场 28 + Tiny 次击杀，这条会明显影响 YELLOW 下的输出，评估里单独统计。
- Q4（两次未预测命中）按 subject 记；支撑认证之前（§3.1）Forum 的未预测命中预期偏多，是 F1 的门槛。
- P1：波间登记为"安全窗口"（类型模板的加载 / 释放、场的全量重算放在这里）。

### 3.8 视觉合法性：每个新组件读什么

| 组件 | oracle 视图读 | 视觉视图的来源（M3） | 现在就守的纪律 |
|---|---|---|---|
| EnemyTracker | Entity.phase（FSM 状态、StateTime） | 每类的可观测阶段表（表里已有 `observable_phases`）+ 阶段内时间 | 跟踪器按 view 分支，规划器只看 `Forecast` |
| 敌人身份 | iid | 检测轨迹 id | 不跨轨迹用 iid 关联 |
| 敌人 HP（集火、击杀冻结） | — | 数看得见的命中 | **不读 ents.hp**（oracle 视图也用计数，和 Bell Beast 视图同法） |
| 波次 | — | 静态波次表 + 看得见的死亡 / 出场 | 不读 `room.battles`（只作测试真值） |
| 投射物 | 实体位置 | 检测轨迹（同 `bell_track`） | 速度用轨迹拟合，不用导出速度 |
| 可拼刀 / 反击 | 静态表 | 静态表；运行时拼刀成败看闪光 / 冻结 | 运行时不读 parry 位 |
| 助战、Cogfly | `allies` 导出位置 | 检测 | 不读它们的 FSM |
| 画面外 | — | Clawmaiden 从 (1.67, 46.23) 飞进、Clapper 从 y 23–26 落下 | 出场模板来自静态出生点 |

每轮照 M2.md 的决定跑一小批 degraded 视图作"有没有偷看后台"的回归（Forum 先做 ObservabilityFilter 的位置 / 框 / 朝向直通和 hp、FSM 屏蔽；可观测阶段表等 M3）。

---

## 4. 计算成本与预算

### 4.1 不改结构的 Forum 估计

| 阶段 | Bell Beast 今天（表 A，p50 / p99） | Forum 朴素扩展（估计） | 依据 |
|---|---|---|---|
| 预测 + 战术 | 0.65 / 3 | 1.5 / 5 | K ≈ 3 个 walk |
| 推演（bounds） | 3.07 / 4.84 | 7–9 / 11–13 | 表 B：Forum bounds 400 × 48 ≈ 512 × 48 × 0.8 |
| 支撑（含命中效果） | 2.24 / 10.73 | 4 / 18+ | K 个类型的查询、K 个目标的命中效果 |
| 其余 | 0.8 / 5 | 1 / 5 | |
| **合计** | 7.2 / 20.2 | ≈ 13 / 35 | 每帧都会超 16.7 ms 的边界 |

### 4.2 增量措施与估计

1. **两段式检查（最大的一项）。** 全部 N 个候选先跑**标称一条线**（Forum 400 × 36：1.17 / 3.16 ms），用每帧 1 个中心点查支撑：标称轨迹碰到支撑的行一定 S = 1（包络 ⊇ 标称线），直接淘汰；同时在标称线上算 J。剩下的按 (V 估计, J) 排序，只有前 K_b = 96–128 行跑**包络**（Forum bounds 96 × 48：1.41 / 3.31，换成 36 帧约 1.1 / 2.5）和包络的点格查询。命中效果、拼刀分支、E / r̂ / O 都只在这 K_b 行上算。安全不变：被选中的计划永远是做完包络检查的。
2. **显式视野 48 → 36 帧（0.6 s）**，0.6–2.0 s 交给终点价值（E、trapped）和 `_tail_pick`；长招仍按 `long_horizon` 延长。推演 ∝ T。
3. **按姿态的候选族**（§3.3）：墙上 80、空中 144、地面 ≈ 400。
4. **walk 缓存**（§3.1）和**场轮转**（§3.4）：每 tick 至多重算一个敌人的场。
5. **命中效果上限 64 行**、**拼刀分支上限 16 行**、**目标包围盒剔除**。
6. **截止时间的 anytime 选择**（§4.4）。

| 阶段 | 估计 p50 / p99（4 线程，训练负载） | 依据 |
|---|---|---|
| 预测 + 战术（walk 缓存） | 0.6 / 2 | Bell Beast 0.65 / 3 |
| 推演：标称 400 × 36 + 包络 96 × 36 | 2.3 / 5.7 | 表 B（p99 相加是上界） |
| 支撑：中心点 + 前 K_b 的包络点格 | 1.2 / 4 | 今天 2.24 / 10.7 中扣掉命中效果尖峰，点数约为今天的一半 |
| 命中效果（≤ 64 行、K_eff ≤ 3） | 0.3 / 2.5 | 今天 0.18 / 8.0，加了上限 |
| 场（一个敌人）+ E / r̂ / O（K_b 行） | 0.5 / 1.2 | 14.7k 点 ≈ 一次 `_contacts` 的量 |
| filter / score / select | 0.8 / 3 | 今天同项 |
| **合计** | **≈ 6 / 12–14** | p99 各项不会同时出现，合计偏悲观 |

**这些是估计**，F4 用 `planner_bench --encounter Forum` 在数据策略录像上开环实测（§6）。

### 4.3 每 tick 的流水线（改后）

```
every frame:
  if committed primitive active and not abort_needed: continue its hold schedule
  s      = state_at(now + L)
  mf     = multi_forecaster.forecast(H = 2.0 s)           # walk 缓存；投射物轨迹
  fields = terminal.update_one(mf)                         # 轮转：0–1 个敌人
  prefs  = gauntlet_tactics(s, mf, fields, playbook, supervisor_flags)
  C      = candidates.for_pose(s.pose, prefs)              # 80–430 个
  nom    = rollout(C, lanes=nominal, T=36)                 # 阶段 1
  S_nom  = mf.occupied(centres(nom))                       # 必要条件
  J_nom  = score(nom, mf.targets, weights)
  B      = top_K_b(C[!S_nom ∧ veto_ok], by J_nom)          # + 上一帧计划 + 它的 V 备选
  hull   = rollout(B, lanes=bounds, T=36)                  # 阶段 2
  S      = contacts(hull) ∪ hit_effects(B) ∪ clash_branches(B) ∪ lock_check(B)
  E, trapped, r̂, O = terminal.eval(B.end_states, fields)
  pick lexicographically (§2); no S = 0 → min P' (P over C), emit FORCED_RISK
  deadline: 阶段 2 按块（32 行）推进，超过截止时间就停在已检查完的块
```

### 4.4 截止时间与 anytime

- 阶段 2 的行按优先级排：上一帧计划（CONTINUE）→ 它的 V 备选 → 上一帧前 16 名平移 → 其余按 J_nom。按 32 行一块推进，每块之后看时间：超过截止（例如 11 ms）就停，只在已检查完的行里选。
- 保证：CONTINUE 和它的备选总在第一块里，所以只要上一帧的计划还安全就有一个完全检查过的选择；若第一块里没有 S = 0 的行而时间已到，照样把下一块做完（安全检查不能省），这是唯一会超时的情况，记入统计。
- 场的轮转、walk 重算在截止时间临近时推迟到下一 tick（它们只影响打分）。

### 4.5 训练与正式运行

训练：4 个实例 × 4 线程，上面的估计按这个口径。正式运行：1 个实例 + 视觉（GPU），规划器可以给 8 线程，推演和查询的 prange 大致线性，估计 p99 再降 30–40 %。

### 4.6 需要你决定的：预算口径

DESIGN §3.5.4 的"≤ 512 × 48、p99 ≤ 3 ms"在 Bell Beast 上已经是 13–15 ms（实战 p99）/ 20 ms（今天的负载下 bench），门槛照样过了。增量路线在 Forum 上估计能做到和 Bell Beast 今天同一水平（p50 ≈ 6、p99 ≈ 12–14 ms），**做不到 3–4 ms**。建议把预算改成可检验的两条：(1) 实战每场迟到帧（late tick 跳过的帧）中位数 ≤ 10、p90 ≤ 30（Bell Beast degraded_dust 门槛跑是 7 / 17）；(2) planner_bench 开环 p99 ≤ 14 ms（4 线程、训练负载）。如果坚持 3–4 ms，需要结构性改动（GPU 推演或学习的候选提议），不在增量方案里。

---

## 5. 数据需求

| 项 | 用途 | 怎么采 | 量 | 现状 |
|---|---|---|---|---|
| D1 用全部 122 场重建 Forum 行为表 | 支撑保守性（留出 anchor 超出 0.5 u ≤ 0.1 %） | `behaviour_build --encounter Forum` 加入 5 个数据运行 | 122 场（现在 13） | 录像已有 |
| D2 冲刺 / 冲刺斩 / Clawline 近身时敌人的反应 | 你观察到的"突然贴近"：后撤、闪避、反击这些招之前没在"贴近"条件下记录过 | 数据策略加 DASH_APPROACH（朝最近敌人冲刺 + 出刀）和 CLAWLINE 段（按键即可，不需要模型） | 每类每个闪避 / 反击招 ≥ 200 | 未做 |
| D3 Envoy 定点采集 | 只在第 0 波出现一只、38 HP；HopSlash 从没出现（要主角在它上方），JumpSlash 15 h、Ambush 44 h | 训练 mod：敌人无敌开关或 HP 置高，只打 Envoy 的 savestate；采集策略站到它上方 | 每招 ≥ 200（Ambush 可按开场固定处理） | 未做 |
| D4 入场家族 | 出场模板 | 用"所有记录 + 状态机分支"的并集加大余量，不要求 200 | 每场 1–5 个 | 现有 |
| D5 拼刀成功率 | §3.5 | 数据策略定时出刀对着可拼层；冻结事件标成败 | 每（类型, 招）≥ 30 起步 | 未做 |
| D6 击杀冻结时长 | YELLOW 的致死一击规则 | 录像里 freeze 事件 × 击杀 | 每类 ≥ 20 | 录像已有 |
| D7 收割者冲刺斩多边形与帧窗口 | §3.3 | 部署 `slash.dump paths`，采 20–40 次 | 40 | mod 已编译未部署 |
| D8 Clawline 运动学 | §3.3 | 反编译 + 激励录像（`kn_excite_forum` 加 harpoon 段） | 拟合 + 留出各 ≥ 100 次 | 未做 |
| D9 Cogfly 出手硬直 | 剧本宏 | 激励录像 | 20 | 未做 |
| D10 风险模型标签 | r̂ | 全部录像（数据策略）+ 规划器实战 | 已有 ≈ 24k 次受击 | 有 |
| D11 惩罚窗口表 | O | 从行为表模板离线算（`punish_tables`） | — | 未做 |
| D12 波次课程 | 评估速度（一场随机策略 12–16 min） | 训练 mod 命令"跳到第 i 波"（BattleScene.StartWave(i) 是公开方法【未核实能否在中途安全调用】）+ 随机化主角状态 | — | 未做 |
| D13 你的 Forum 手打录像（可选） | 站位参照（每波你站在哪）、每秒按键数对比 | 你方便时录一场 | 1–3 场 | — |

---

## 6. 实施计划（按顺序）

| 里程碑 | 内容 | 交付 | 验收 | 依赖 |
|---|---|---|---|---|
| **F0** 基线 | 本文的三项测量入库为工具；`planner_bench --encounter Forum`（数据录像开环，先用单敌包装测管线） | 工具 + 基线数字 | 能在 3 个波次组合（Maestro 波、混合波、终局）上各跑 8,000 tick | — |
| **F1** 多敌预测 | `EnemyTracker`、`MultiForecaster/MultiForecast`、按类型查询与懒加载、walk 缓存、死亡尾巴、确定路径投射物、`support_set` 按实例；D1 重建表 | 代码 + 单元测试 | (a) 包住单个 Bell Beast `Forecaster` 时逐位相同；(b) `support_recall --encounter Forum` 在留出场次：滞后 2 / 3 / 4 帧接触召回 100 %（带 `margin_type`），每类留出 anchor 超出 0.5 u ≤ 0.1 % 后去掉 margin；(c) 投射物轨迹审计：中心误差 p99 ≤ 0.3 u | D1 |
| **F2** 多目标命中 | 受击框路径表、K 目标打分与命中效果、击杀 / 反击 / 打铃分支、集火权重 | 代码 + 属性测试 | `predict_audit` Forum：侧砍 / 上砍 / 下劈命中预测 FP ≤ 2 %、FN ≤ 5 %；危险区不变式（击杀、打铃、拼刀弹开）违反 0 | F1 |
| **F3** 新原语 | 冲刺两处修复；`M_DASH_STAB`、`M_HARPOON`；姿态候选族；`pocket_macro` | 运动学 + 候选 | `kin_check` 新留出录像：每类 ≥ 99 %（含 dash、dash_stab、harpoon）；冲刺斩多边形命中核对 TP / FP 同 Reaper 横砍；口袋宏在 `kn_forum_wall` 成功率 ≥ 95 % | D7 D8 |
| **F4** 算力重构 | 两段式、T 36、截止时间、上限 | 代码 | `planner_bench --encounter Forum` p99 ≤ 14 ms（4 线程，训练负载）；Bell Beast 回归：bench 不慢于今天，oracle 实战 50 场 ≥ 97 % CLEAR、0 WOULD_DIE | F1–F3 |
| **F5** 终点价值 | 占据场、可达模板、E / trapped、r̂、O、惩罚窗口表 | 代码 + 拟合 | r̂ 留出 AUC ≥ 0.75、校准误差 ≤ 0.05；离线回放：FORCED_RISK 前 1–3 s 有"可避免它的站位"的比例（DESIGN §3.5.7 事后审计）比 F4 低 | F4 D11 |
| **F6** 剧本与战术 | `Forum.yaml`、`GauntletTactics`、`WaveTracker`、监督器小改 | 代码 + YAML | 波次跟踪与 `room.battles` 比对 100 %；波次课程每组 ≥ 50 起点：每波受击数有基线；终局口袋 100 次里 Clapper 在口袋内的命中 0 | F5 D12 |
| **F7** 拼刀 | 分层模板、`EV_CLASH`、成功率测量、A/B | 代码 + 剧本条目 | 整场 A/B（每组 ≥ 200）：开的一组受击 / 退出不更多才保留 | F6 D5 |
| **F8** 门槛 | 全程 Forum 序贯贝叶斯门槛（oracle 视图）；助战组和后备组；小批 degraded 回归 | 门槛报告 + K1 输入 | ≥ 70 % CLEAR、WOULD_DIE 上界 ≤ 1 %（0 次需要约 300 场）；K1 按 M2.md | F7 |
| F9（可选） | DESIGN §3.5.3 的"可反应"放宽：前摇足够长（tell_lead ≥ L + esc + 2 帧）的未开始分支不要求整段回避，只要求在它可能开始时有安全的躲法 | 代码 | 只有当 F8 的 FORCED_RISK 事后审计显示"多个待机敌人的并集"是退出的主因时才做；离线反应性证明同 `tools/reactability` | F8 |

F1 和 F3 可以并行；F2 依赖 F1 的目标接口；F4 在 F1–F3 合入后做，F5 的场依赖 F4 的两段式（E / r̂ / O 只在 K_b 行上算）。

---

## 7. 评估方案

### 7.1 协议

1. **波次课程**（需要 D12）：按波次组合分组（混合波 0 / 3 / 8 / 9 / 11、Minister 波 4、Clawmaiden 波 5 / 10、Maestro 波 6 / 12、Clapper 波 7 / 13），每组随机化主角位置 / HP / 丝，≥ 50 起点做开发、≥ 200 起点做 A/B。
2. **全程连战**：oracle 视图，savestate fo_A（Reaper + 爬墙爪 + 助战）为主，fo_B（Hunter_v2 + 助战）、fo_C（无助战，后备）、fo_A5（5 面具）各一组；时间盒 1500 s。
3. **门槛**：序贯贝叶斯（同 Bell Beast 的 `bayes_gate`）；WOULD_DIE ≤ 1 % 要在 0 次时约 300 场（3/n 法则），按规划器一场约 8–10 min 估计 4 实例约 10–12 h。
4. **视觉纪律**：每轮小批 degraded 回归（不在模拟视觉上精调）。

### 7.2 A/B 组

| 组 | 比较 | 主指标 |
|---|---|---|
| 终点价值 | 关 / 只 E / E + r̂ / E + r̂ + O | 每波受击、FORCED_RISK 频率 |
| 集火 | 关 / 击杀价值 / + focus | 每波用时、敌人在长招里的占比 |
| 新原语 | 无冲刺斩与 Clawline / 有 | DPS、每波用时、受击 |
| 拼刀 | 关 / 开（按类型 × 招组） | 受击、WOULD_DIE 上界、退出 |
| 终局 | 口袋 / 地面 | 终局受击、用时 |
| Cogfly | 第 6 波 + 终局 / 按需 | 用时 |
| 助战 | fo_A / fo_C | 全程（K1 的输入） |

### 7.3 指标定义

- **每波受击数**：damage 事件按波次跟踪器归波；另记 damage_blocked。
- **FORCED_RISK 率**：tick 占比和"每场出现过的段数"；**事后审计**：每次 FORCED_RISK 往前看 1–3 s，离线重放所有候选，统计当时是否有能避免它的站位（DESIGN §3.5.7）。
- **敌人在长招里的占比**：敌人帧里处于攻击家族状态的比例（相对决策 / 待机），按类型；你的"好的局面是怪都在长招里"的直接度量。
- **DPS**：主角造成的伤害 / 在战秒（分开钉子、丝矛、助战、Cogfly）；每波用时。
- **按键经济**（M2.md）：每秒按键数、按键提前量分布、计划改动率（已决定的按键在执行前被改掉的比例）、同帧抖动次数；对比你的录像（如有）。
- **监督器**：退出按 Q 类型、Bind 次数和成功率、"受击后 2 s 内有够回血的窗口但丝不够"的次数。
- **预测检验**：未预测命中（按 subject）、命中预测混淆矩阵、r̂ 校准。

---

## 8. 主要风险与缓解

| # | 风险 | 后果 | 缓解 |
|---|---|---|---|
| 1 | Forum 支撑不保守（留出 0.3–5.2 % 接触在 0.5 u 外） | 未预测命中、Q4 退出、WOULD_DIE | F1 先用 122 场重建并以召回为门槛；未认证前按类型加余量、`known=False`；结构性补洞（Clawmaiden 瞬移落点用 Teleplane 区域 x 17.42–45.94、y 7.35–13.26 的并集）；实战监视未预测命中 |
| 2 | 多个待机敌人的并集太宽 → FORCED_RISK 多 → 不敢出刀、h = 2 后攒不到丝 | CLEAR 低 | 确定路径投射物、walk 只按记录过的分支；终点价值把主角带到不被夹的位置；F9 的可反应放宽作为后手 |
| 3 | 算力（Forum 推演 2.5 倍、K 个目标） | 迟到帧、反应慢 | §4 的两段式与上限、截止时间；F4 有量化验收；预算口径请你定（§4.6） |
| 4 | 新原语模型不准（冲刺留出 97.34 %，冲刺斩、Clawline 尚未建模） | 冲刺进支撑的误判 | 先修两处已知错误；新原语在 kin_check ≥ 99 % 之前不进候选（只进数据策略） |
| 5 | 口袋贴墙起跳漏洞（最近 0.87 u） | 终局受击 | 剧本两条规则 + 支撑覆盖近墙起跳的检查（forum.md §10.4）；终局 A/B 口袋 / 地面 |
| 6 | 拼刀成功率在 oracle 偏高，视觉更低 | 拼刀组在视觉下更差 | 按视图分开实测；F7 只在 A/B 赢了才保留 |
| 7 | 助战改变敌人行为（敌人追 Garmond） | 行为表的概率偏（支撑不受影响：分支取并集） | 检验"有无 Garmond"条件；fo_C 后备组单独建概率 |
| 8 | 一场太长（随机策略 12–16 min），评估慢 | 迭代慢 | 波次课程（D12）；门槛只在全程跑 |
| 9 | 击杀冻结吞暂停，YELLOW 下少打致死一击 → 用时变长 | h = 2 时更久 | 每类实测冻结时长；只有支撑里冻结 + 0.3 s 内无威胁时才打可能致死的一击 |
| 10 | 风险模型 r̂ 从随机策略数据学到的是"随机打法的风险" | 打分偏 | 规划器上线后在它自己的录像上重拟；只进 J / P，不碰 S |
| 11 | 内存（9 类模板 × 4 实例） | 实例 OOM | 按波懒加载；F1 实测每类体积 |
| 12 | `StartWave(i)` 中途调用不安全 | 课程不可用 | 退回：从开场 savestate 用"加速清前面波次"的训练命令（敌人一击死）跑到第 i 波 |

---

## 9. 需要你决定的

1. **预算口径**（§4.6）：改成"迟到帧 + bench p99 ≤ 14 ms"，还是坚持 3–4 ms（那就需要增量之外的结构性改动）。
2. **训练用 mod 命令**：跳到第 i 波（D12）、敌人无敌 / HP 置高（D3）。只在训练副本用。
3. **Cogfly 的默认分配**（第 6 波 2 次 + 终局 2 次，还是全留给终局）：按 A/B 定，可以先听你的经验。
4. **你的 Forum 手打录像**（可选，D13）：站位参照和按键数对比。

---

## 附录 A：本文的测量怎么复现

- 表 A：`cd brain; ../scripts/uv.cmd run python -m ssbot.tools.planner_bench C:/ssbot/data/runs/m2/20261003_144536_BellBeast_eval_planner_oracle/rec/2026-10-03/TRAIN/i4_000 --frames 8000 --threads 4 --json <out>`（below-normal 优先级，同机有游戏实例和其他代理）。
- 表 B：`../scripts/uv.cmd run python -m ssbot.tools.kin_bench_forum --n {512,400,128,96} --T {48,36} --reps 200 --threads 4 --lanes nominal,bounds,bounds_lo`。
- 表 C：会话临时目录 `forum_simul.py`（未提交）：`behaviour_tables.run_fights` 取 CLEAR 的场，`RecordingReader.states(f_wake, f_end, keys=("f","ents","hero"))` 每 6 帧取样；"在战" = `gauntlet.live_enemies` 且该类 Control FSM 状态不在 `FORUM_SPECS` 的 dormant / rest 里；波次按 AttemptRecord 的 `gauntlet.waves` 帧号。F0 把它做成 `tools/forum_simul.py`。
