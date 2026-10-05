# Forum 规划器扩展：两份设计的评审与合成计划

2026-10-03，评审 / 合成代理。分支 `design-forum-plan`（基于 main 9d86e71）。评审对象：

- **I（增量方案）**：分支 `design-forum-incremental` 22716b6，`docs/plans/forum_design_incremental.md`
- **H（分层方案）**：分支 `design-forum-hierarchical` 504e6d1，`docs/plans/forum_design_hierarchical.md`

依据：DESIGN §3.5（尤其 §3.5.3 支撑 / 概率、§3.5.4 规划器、§3.5.6 Bind / 拼刀及 10-02 / 10-03 修订、§3.5.7 你 10-03 关于多敌站位的五点）、§3.7.4（Q1 / Q1a / Q6 修订）；`docs/plans/M2.md`；facts `forum.md`、`movement_kinematics.md`、`m2_vision_view.md`、`probes.md`；main 9d86e71 的代码。本文没有改代码，没有连接游戏；测量全部离线、低优先级（附录 A）。"【未核实】"是没有证据的说法；"估计"写明依据。

---

## 0. 结论（一页）

**选哪个骨架。** 两份设计在安全语义上一致（支撑决定 S，概率只进 P / J，字典序不变，新代码只读视觉可得的信息），差别在"站位、诱敌、各个击破"这些 1–4 s 的决策放在哪里：I 放进规划器的终点价值（每个候选的推演终点在敌人占据场上查 E / O / 击杀价值）加一层薄的 L2 规则；H 新建一个 5 Hz 的战术层，在抽象状态上搜索"目标"，再通过 J、候选组成和视野影响快层。

H 总分略高（§3），但它多出来的分——监督器耦合（Q3 多段、最后一击的 I3）、"打分不碰安全"的属性测试、A0 基线、按 bounds_lo 定预算、成对种子——都不依赖它的骨架，可以原样搬过来；它扣分的地方（实施量、调参量、两层打架）恰恰来自骨架。所以：

- **骨架用 I**：一个滚动视野规划器 + 多敌预测（`MultiForecast` 与今天的 `Forecast` 同接口）+ 终点价值（逐行查占据场）+ 两段式推演 + 截止时间。
- **从 H 嫁接**：A0 基线轮次；核心躲避集永远在、永远做包络检查；目标仲裁的有效条件 / 寿命 / 被挡禁忌 / 滞回（做成 L2 的一部分，不做 4 s 抽象搜索）；h 暴露项 H；Q3 多段与最后一击 I3 / U 的移植；按 bounds_lo 定预算；成对种子与消融；场的时间膨胀（粗格空 ⇒ 细查询空）。
- **两份都改**：支撑认证是 Forum 一切实战评估的前置（未认证 = 全程 YELLOW + h = 2 就 Q3，§1 第 4 条）；全部 9 类模板放进一个 `SupportQuery`（实测 384 MB / 进程，不需要按波懒加载）；"不被困"先进 J，不改字典序。

**评分**（10 分制，§3）：I 安全 7 / 表现 7 / 算力 6.5 / 风险与时间 7.5 / 可检验 7 = **35**；H 8.5 / 7.5 / 7 / 5 / 8.5 = **36.5**。

**算力。** 本次复测与两份设计的数字一致（Bell Beast 整 tick p50 6.7 / p99 20.4 ms；Forum 推演 2.3–2.4 倍于 Hunter）。合成方案估计 Forum tick p50 ≈ 8 ms、p99 ≈ 15–17 ms（不加截止时间），加截止时间后 p99 ≈ 13–15 ms。**3–4 ms 做不到**（两份设计都这样认为，复测支持）。提议 M2 Forum 期的目标：实战每场 tick p99 的中位数 ≤ 15 ms、每场迟到跳帧中位数 ≤ 10（Bell Beast 门槛时 12.7–14.6 ms、7 帧），请你定（§9）。

**实施**：11 轮（R0–R10，§5），每轮有验收测试；门槛 ≥ 300 场完整连战（0 次 WOULD_DIE 时才能说上界 ≤ 1 %）。

**问你的**：§8 的 13 个游戏经验问题（最后一个可选）（多段攻击连上掉几格、Minister / Reed 防御姿态、哪些招值得拼刀、冲刺斩和飞针用在谁身上、贴墙能否 Bind、终局慢动作、Garmond、Cogfly、波前站位……）；§9 的 4 个决定。

---

## 1. 两份设计与代码的核对

| # | 说法 | 出处 | 核对结果 |
|---|---|---|---|
| 1 | 字典序 `not Hz > not Hz_soft > not U > S = 0 > 保持已承诺的跳 > comfort > V > min P > 最晚首次接触 > max J`；P 只在 FORCED_RISK 时算 | I §1.1、H §1.4 | 对（`planner.py:434` 的 lexsort；P 在 :415 只在 forced 时算）。I 漏了"保持已开始的宏"（`mkeep`）一级，不影响结论 |
| 2 | 候选 = 21 首原语 × 17 续接 = 357 | I §1.1、H §1.3 | 文档串过时：续接现在是 21 个（多了 4 个 `upatk`），**实际 441 + CONTINUE**（本次 `bench_tick` 读到 `N_cands = 441`）；所以"Forum 地面族 ≈ 400"并不比今天多 |
| 3 | `Forecaster` 可注入通用跟踪器，"小改"，Bell Beast 逐位不变 | I §3.0 | 可行但不是小改：`Forecaster.__init__` 内部建 `BossTracker`，walk（`_walk/_place/_successors`）读 Bell Beast 的 `Ctx`（direction / phase / raged / hp），还有落铃、攻击铃、冒烟前兆。合成方案按 H 的做法：**不改单 Boss 路径**，新写 `EnemyTracker` + 把与 Boss 无关的 walk / place 抽成函数，Bell Beast 由现有逐位测试锁住 |
| 4 | 支撑未认证的类型标 `known=False`、加余量先跑 | I §3.1 | **这条行不通**：`SupportSet.known = False` 时监督器加一个 "unknown" 事件，**h = 2 就 Q3、风险档永远到不了 GREEN**（`supervisor.py` 文档串 12–20 行）：全程 YELLOW（惩罚最多 1 击、不弹反、不打可能致死的一击）。所以支撑认证（留出召回 100 %，含按类余量）是 Forum 实战评估的前置，不能边跑边认证（H 的 F1 硬门槛是对的） |
| 5 | 多段攻击按整链伤害计 | I §3.1、§3.7 | 不完整：`q3_threat`（`supervisor.py:356`）对 `hits > 1` 的事件在 h = 2 时**退出**。Choristor 鞭、Reed ParrySlash、Minister Slash 在第 0、1、2–4、8–12 波都有；按现规则，h = 2（7 面具、D1 = 2 时 HP 3–4）只要这些怪在 0.8 s 支撑里就退出。**H 指出了（§5.6 的 H 项、附录 B 第 3 条），I 没有**。这会是 Forum QUIT 的大头之一 |
| 6 | U（可能致死的一击）不变 | I（未提） | `unpausable(may_kill)` 只看单个 Boss 的 hp（`planner.py:1053`）。Forum 最后一个波次成员死时有 1.85 s 的 `EnemyBattleEndSlow`（I3 提交区，forum.md §3），之后 4.1 s 内垂死本体、rune、炸弹照样伤人。**H 把 U 移植到"可能打死本场最后一个波次成员的一刀"，并考虑了 Garmond 抢最后一击；I 没有** |
| 7 | 推演用 bounds（9 条） | I §4 | facts 的结论是 Forum 与 Hunter 的安全检查都该用 **bounds_lo**（10 条，movement_kinematics §5.5），但 `PlannerConfig.variants` 仍是 "bounds"（`planner.py:126`）。I 的预算按 bounds 算，低估推演约 1.2–1.3 倍；H 按 bounds_lo。合成按 bounds_lo |
| 8 | 9 类模板 × 4 实例内存不可接受，要按波懒加载 | I §3.1、风险 11 | 实测（13 场建的表）9 类打包后合计 **384 MB / 进程**（最大 Clawmaiden 79 MB、Reed 63 MB、Tiny 58 MB、Clapper 58 MB），加载 + 膨胀合计约 7 s；4 实例 1.5 GB，加舒适度模板约翻倍【估计】，64 GB 内存放得下。**不需要懒加载**；全部 9 类放进一个 `SupportQuery`，每个阶段一次查询（少几次 numba 调用） |
| 9 | 占据场 1,050 格 × 14 时间格，一个敌人 0.3–0.5 ms | I §3.4 | 实测（Bell Beast 的 2 s 预测当作一个敌人）p50 0.36 / p99 1.37 ms：p50 对，p99 约 3 倍 |
| 10 | 粗格按格对角线一半膨胀 ⇒ "粗空必然细空" | H §7.1 | 只管了空间。时间格 0.2 s 只在格点采样，格点之间的占据会漏；要按时间并（`SpaceTimeTemplate.dilated(t_bins=…)` 已有）。粗格只进打分，不影响安全，但照原写法属性测试会失败 |
| 11 | 两段式在 192 规模收益不大，先不做 | H §8.2 | 对（192 + 64 vs 192 直接包络）。但它的前提是把候选砍到 ≤ 192；合成方案保留 ≈ 400 个候选，两段式就是必须的。本次在 Bell Beast 真实候选上实测：标称 441 行 + bounds_lo 前 96 行 p50 2.0 ms，对比 bounds_lo 全部 441 行 3.85 ms（Hunter 参数） |
| 12 | 按波 savestate 做开发期 A/B | H §13、§14 | 【未核实，可能不成立】：DebugMod savestate 存 PlayerData、场景和位置；`BattleScene` 的当前波次是场景运行时状态，读档会重载房间，大概率回到开战前。I 的"训练 mod 命令 `StartWave(i)`"同样未核实。两条都放进 R1 的可行性探针 |
| 13 | 战术层与规划器同线程分片，确定性 | H §5.5 | 对且重要：numba 核没有 `nogil`，离线重放（`view_compare`、`postmortem`）要能复现。合成方案的场轮转和 L2 都按固定计划分片 |
| 14 | 冲刺、滑翔、贴墙、爬墙、Reaper 下劈已建模；冲刺斩、飞针没有；`attacks/reaper.json` 已有；`SafeSpot.usable` 要求 `kind == "floor"` | I §3.3、H §8.1 | 对（`kin_jit.py` 有 `M_DASH / M_SPRINT / M_GLIDE / M_SCRAMBLE / M_RPR_DS`；`playbook.py:39`）。另：`candidates.py` 没有 DASH 和墙上原语；`planner.py` 的攻击框是 Hunter 常量（`SIDE / UP / DOWN`），Reaper 形状要接进 `_score_kernel` |
| 15 | Forum 录像 122 场（I）/ 128 场（H） | | 现在 CLEAR 的完整连战 128 场（2 + 1 + 10 + 25 + 19 + 35 + 36，按各运行的 attempts 计），行为表只用了 13 场 |
| 16 | 每波同时在战的敌人数 | I 表 C、H §1.2 | 两份口径不同（I 去掉了 Clapper 的 Idle，H 用 `in_play`），结论一致：中位 2–3 个、最多 8 个（第 6 波两只 Maestro + 6 只 Tiny）；"混合"（有的在招里、有的待机）是最常见局面（H：39–75 %）。H 的表（12 场、609,481 帧）更完整，合成方案用它 |

---

## 2. 本次复测（离线，低优先级，整机有游戏实例和其他代理在跑）

**表 A：Bell Beast 规划器 tick**（`bench_tick.py` = `planner_bench` 加测量项，录像 `20261003_144536` i4_000 前 4,000 帧，3,951 tick，oracle，4 线程，ms，p50 / p99）

| 项 | 本次 | I 测 | H 测 |
|---|---|---|---|
| 整 tick（预测 + 战术 + 规划器） | 6.72 / 20.4 | 7.19 / 20.23 | 7.0 / 19.6 |
| 规划器 | 5.93 / 16.79 | 6.55 / 17.16 | 6.52 / 16.93 |
| — 推演（bounds，441 + 1 行 × 49） | 2.84 / 4.30 | 3.07 / 4.84 | 3.05 / 4.69 |
| — 支撑（含命中效果、锁定、舒适度） | 2.09 / 10.56 | 2.24 / 10.73 | 2.24 / 10.38 |
| — 其中命中效果重推 | 0.17 / 7.42 | 0.18 / 8.01 | 0.19 / 7.62 |
| 预测 `update + forecast(2 s)` | 0.16 / 0.62 | — | 0.10 / 0.49 |
| 战术 `Tactics.decide` | 0.41 / 3.82 | — | 0.26 / 3.53 |

三次测量一致：p99 的大头是命中效果重推（两份设计都给它设上限，I 64 行、H 24 行）。

**表 B：Forum 运动学**（`tools/kin_bench_forum`，合成墙房间、随机按键，4 线程，120 次，ms，p50 / p99）

| 规模 | nominal | bounds | bounds_lo | Hunter bounds_lo |
|---|---|---|---|---|
| 512 × 48 | 2.35 / 4.90 | 8.55 / 12.81 | 11.68 / 16.68 | 4.96 / 6.44 |
| 400 × 36 | 1.76 / 3.70 | 5.35 / 8.60 | 6.90 / 10.77 | 2.86 / 4.12 |
| 192 × 48 | 1.09 / 2.38 | 2.57 / 4.76 | 4.62 / 7.42 | 1.90 / 2.98 |
| 128 × 36 | 0.47 / 1.39 | 1.31 / 3.16 | 1.44 / 3.59 | 1.11 / 2.15 |
| 96 × 36 | 0.38 / 0.94 | 1.06 / 2.43 | 1.37 / 3.14 | 0.55 / 1.99 |

与两份设计和 movement_kinematics §6 一致：Forum bounds_lo 是 Hunter 的 2.3–2.6 倍；小批量（≤ 128 行）固定开销明显。

**表 C：两段式在真实候选上**（同表 A 的录像，规划器自己的 441 行，Hunter 参数，ms）：标称全部 441 行 0.98 / 2.0；bounds_lo 前 96 行 1.04 / 2.27；对比今天的 bounds 全部 2.87 / 4.34、bounds_lo 全部 3.85 / 5.43。两段式省约一半。

**表 D：终点价值的场**（同录像，Bell Beast 的预测当作"一个敌人"）：I 的栅格（0.5 u × 1 u，1,050 格 × 14 个时间格 0.7–2.0 s，2 s 预测）0.36 / 1.37 ms；H 的栅格（1 u，490 格 × 20 个时间格到 4 s）0.49 / 3.44 ms，外加 `forecast(4.0)` 0.23 / 0.91 ms。

**表 E：Forum 模板与查询**（`forum_tpl_bench.py`，读工作区 wf_946a7803-63c-2 里 13 场建的 `*_hitboxes.npz`，只读）：9 类打包合计 384 MB / 进程（见 §1 第 8 条）；一类模板、400 行 × 37 步的中心点查询：20 / 60 / 150 个放置 p50 0.3 / 0.5 / 0.8 ms、p99 0.8–2.1 ms；192 行约 0.6 倍。随机放置比真实 walk 分散，只当量级。

---

## 3. 评分

| 维度 | I | H | 理由 |
|---|---|---|---|
| 安全（支撑决定、无新的放行路径、视觉合法） | **7** | **8.5** | 两份都只让新东西进 J / P、最终选中的计划都做完整包络检查。I 扣分：漏了 Q3 多段在 h = 2 的退出、漏了最后一击的 I3 / U、把"未认证支撑先跑"当可行（§1 第 4–6 条）；可选的 F9"可反应放宽"会动支撑语义（DESIGN §3.5.3 允许，但视觉前兆时长要 M3 才能测）。H 加分：四条"目标不碰安全序"属性测试、注入失败逐位不变、核心躲避集、I3 移植与 Garmond 抢最后一击、h 暴露项；扣分：粗格的时间膨胀漏洞（只影响打分）、按波 savestate 的前提可能不成立 |
| Forum 表现（被夹、扎堆、待机怪、诱敌、集火、口袋、新原语、拼刀） | **7** | **7.5** | 两份都覆盖了你的五点：E / 被困（被夹、墙角、刷怪点）、危险区重叠（扎堆）、待机按最快一击核验（支撑本来就做）、每招惩罚窗口 × 出招概率（诱敌）、留一法击杀价值 + 各个击破（集火）、口袋两条规则、拼刀两分支。I 加分：确定路径投射物（Bell Beast 上 FORCED 57.7 % → 9.6 % 的经验）、新原语族更早进候选。H 加分：两步目标"A 放长招去打 B"、SPLIT 借 Garmond、h 暴露项会直接减少 Q3 退出（对 CLEAR 率影响大）；扣分：候选砍到 ≤ 192 且按目标给族，目标错了好选项就不在场；冲刺斩 / 飞针放到最后 |
| 算力的现实性 | **6.5** | **7** | 两份估计的量级都被复测支持，也都承认 3–4 ms 做不到。I：两段式是实测有效的杠杆（表 C），但预算按 bounds、内存担心过度、场的 p99 偏乐观。H：按 bounds_lo、测得更全；战术层每帧 p99 4 ms 是代理推算 |
| 实施风险与时间 | **7.5** | **5** | I 每一步都能单独交付和验收，改动集中在已有文件。H 新增 `combat/tactical/` 六个模块、约 10 个目标种类、8 个价值权重 + 滞回 / 寿命 / 被挡阈值，要 CMA-ES 拟合，还要处理两层打架；第一次看到收益要到 F4 |
| 可检验性 | **7** | **8.5** | I 每步有离线验收（召回、predict_audit、bench、kin_check）。H 多了 A0 基线、消融、成对种子、`goal_audit` / `forced_audit`、属性测试和注入失败测试 |
| **合计** | **35** | **36.5** | |

---

## 4. 合成方案

### 4.1 总体

```
WorldState（oracle 或视觉等效视图）
  ├─► MultiForecaster（每帧 update；每个在战敌人一个 EnemyTracker；确定路径投射物；入场模板；死亡尾巴）
  │      ├─► SupportSet（每个实例一个事件；多段事件 hits > 1）──► Supervisor（规则不变，数据来源变了）
  │      └─► EnemyFields（每个敌人一张占据场，按固定计划每帧轮转 1 个）
  ├─► WaveTracker（静态波次表 + 看到的死亡 / 出场 → 当前波、下一波开始区间、刷怪点）
  ├─► L2 GauntletTactics（10 Hz + 事件，分片）：目标 ENGAGE / FOCUS / BAIT / SPLIT / POSITION / PRE_WAVE /
  │      POCKET / HEAL / COGFLY / LOCAL；GoalArbiter（有效条件、0.6 s 寿命、被挡 12 帧 → 禁忌 1 s、滞回）
  │      └─► TacticPrefs 的扩展：2D 站位区域、每个敌人的命中权重、自适应视野、Bind、额外宏
  └─► L1 Planner（60 Hz）：候选 = 姿态族 ∪ 核心躲避集 ∪ 目标宏 ∪ CONTINUE ∪ Bind 宏
         阶段 1：标称推演全部行 + 中心点支撑（必要条件）+ 标称打分
         阶段 2：bounds_lo 包络（核心集里通过阶段 1 的 + 前 K_b + CONTINUE + 它们的 V 兄弟），按 32 行一块
         命中效果 / 拼刀分支 / 终点价值只在阶段 2 的行上算
         字典序不变：not Hz > not Hz_soft > not U > S = 0 > keep > macro > comfort > V > min P > t_hit > max J
```

- **不变**：每帧重规划、支撑决定 S、概率只进 P / J、HoldFilter 与按住时序承诺、锁定检查、尾部检查（`_tail_pick`）、Bind 宏、ABORT、安全过滤器、监督器的 Q 规则（数据来源变了）、永不学习的部分（DESIGN §3.5.8）。Bell Beast 路径不动（Forum 开关关时逐位相同）。
- **J 的新项**（全部只是打分）：`J = Σ_k w_k·hits_k + J_other + w_E·E − w_trap·trapped − w_H·H_exp + w_O·O + w_K·K_kill − w_r·r̂ + 波次项`。FORCED_RISK 时 `P' = P + λ·r̂` 作次级排序（r̂ 上线后）。

### 4.2 你的每一点在方案里落在哪

| 问题 | 做法 | 来自 |
|---|---|---|
| **被夹 / 退到死角 / 站在刷怪点**（§3.5.7 第 1 点） | 每个敌人的占据场 F_i（0.6–2.0 s 每 0.1 s、2.0–3.0 s 每 0.2 s；0.5 u × 1 u 栅格；按格半对角线和半个时间格膨胀，所以"场空 ⇒ 细查询空"）。推演终点按姿态查可达模板 R_t（离线用 Forum 运动学生成），E = Σ_t w_t·\|R_t \ ∪F\|/\|R_t\|；trapped = 存在 t ≤ 1.4 s 使 R_t ⊆ ∪F。下一波的入场模板（WaveTracker 给开始区间）进场和支撑，刷怪点自然被避开 | I §3.4、H §5.3 / §7.1 |
| **扎堆不好、要分开**（你的纠正：判据是危险区和危险时段是否重叠、是否留出安全出刀空档） | 重叠 = R ∩ {Σ_i F_i ≥ 2}；分割系数 solo_i = 1 − i 的惩罚格里被其他敌人场占据的比例；L2 的 SPLIT 目标选使两只支撑分到两侧、中间留空档的位置（可借 Garmond 接一只） | I §3.4、H §5.2 |
| **不出招才危险** | 安全由支撑保证（待机敌人的支撑含所有下一招，锁定检查覆盖整个后摇）；L2 / O 里先手按每类"待机 → 最快一击"的时间和距离核验；EnemyAbs 的 `t_strike`、`windows`（H）作为 L2 的特征 | DESIGN §3.5.7 第 4 点、H §5.1 |
| **诱导长招** | 惩罚窗口表 Pun_a[dx, dy]（每类每招，"出刀 + 后摇"完全落在该招支撑外且刀够得着的秒数，所有招都算）；O_i = 已承诺：剩余窗口；待机：Σ_a p_i(a \| 距离档, 高度档, 主角状态)·Pun_a·γ^Δt（行为表的距离条件）。L2 的 BAIT 目标 = O_i 最大的距离带 | I §3.4、H §5.2 |
| **各个击破** | 击杀价值 K_k = 留一法（去掉 k 后主角周围 ∪F 缩小量）÷ 还需几刀（hp_est / 每刀伤害）；FOCUS 目标：其它敌人 `t_min` 都 > T_focus 时盯一只；剧本类型优先级作乘子（Clawmaiden 偷丝最高） | I §3.2、H §5.2 |
| **左墙顶口袋**（终局两只 Clapper） | POCKET 目标（只在终局）+ 两条规则作有效条件和否决（爬上去前没有 Clapper 本体左沿 ≤ 14.6；在口袋里时面朝左、pos x ≤ 18 的 Clapper 按威胁）+ 快层照常支撑检查；爬墙宏 `CLIMB_POCKET`（离线用运动学找序列，成功率验收）；墙砍够距实测前只按 7 次命中的下界 4.0–4.3 u。**贴墙 Bind 未核实前口袋不当回血点** | I §3.6、H §10 |
| **怪控制距离，要冲刺斩 / 飞针近身** | DASH（修贴墙冲刺、Sprint Grace 两处后 ≥ 99 %）在 R3 进候选，先用"冲刺 + 普通攻击"；冲刺斩（`M_DASH_STAB`）和飞针（`M_HARPOON`）在 R7 建模，留出 ≥ 99 % 才进候选；数据策略 v2 先采"突然贴近时敌人的反应" | I §3.3、H §8.1 |
| **降低风险的动作** | 确定路径投射物（Throwing Bell 含 Tink 改向、Reed 标枪、Clapper 炸弹列、rune slam）；击杀在命中分支里移除该敌人支撑（死亡尾巴之后）；打铃改向；一致性属性测试"效果已知的动作不能让危险区变大"推广到击杀、打铃、拼刀弹开 | I §3.2、M2.md |
| **拼刀** | 可拼层 / 不可拼层分开的模板；刀的有效帧碰到可拼层 → 两分支（成功：该招余下模板撤掉 + 0.15 s 弹反无敌 + 冻结 + 取消后摇；失败：照常）；S 取失败分支，P = p_fail × 失败分支接触概率；成功率按（类型、招、视图）实测；白名单照旧；整场 A/B 决定开关 | 两份相同，DESIGN §3.5.6 |
| **h = 2 先回血、攒丝**（Q1a / Q6 修订） | HEAL 目标（原地 Bind 提交测试通过，或去已核验的安全点）；Q6：`heal_first` 且丝 < 9 时给普通攻击命中加分，**同时 H_exp 项让主角远离多段攻击源和 2 格源**（否则 Q3 退出），去打单段的 Bellbearer、Maestro、Tiny 攒丝 | H §5.6 |
| **最后一击**（1.85 s 慢动作不可暂停） | U 移植为"可能打死本场最后一个波次成员的一刀"（hp_est − 3σ ≤ 本刀伤害），I3 要求满血、h ≥ 3；终局最后一只低血时 L2 先排 HEAL；主角不满血时远离 / 留在口袋（Garmond 可能抢最后一击）；死亡尾巴覆盖垂死本体 | H §5.6 |
| **按键经济** | 目标滞回 + 寿命 + 被挡禁忌；规划器的"保持上一计划"加分；按键提前量和计划改动率进 `fight_stats` | H §7.5、M2.md |

### 4.3 接口（合成）

```python
# combat/enemy_tracker.py（新）：一个敌人实例；BossTracker 不动
class EnemyTracker:
    def __init__(self, model: BossModel, view: str, iid: int): ...
    def update(self, ws: WorldState) -> Entity | None
    def roots(self, origin_t: float) -> tuple[list[Root], bool]   # 与 BossTracker.roots 同形
    hp_est: float; hp_sd: float                                    # 只数看到的命中（两种视图都不读 ents.hp）

# combat/multi_forecast.py（新）
class MultiForecast:                     # 与 Forecast 同名同义，规划器不需要知道敌人数
    subjects: list[Subject]              # iid, type_key, alive, committed, family, hp_est, t_free, t_strike
    def occupied(self, x, y, tk, comfort=False) -> np.ndarray          # [N, T]，全部类型一次查询（OR）
    def occupied_without(self, x, y, tk, exclude) -> np.ndarray        # exclude：subject iid 或投射物
    def prob(self, x, y, tk) -> np.ndarray                             # 1 − Π(1 − p_i)，只进 P / J
    def t_min(self, x, y, t_max=3.0, subject=None) -> float
    def committed(self) -> "MultiForecast"
    def support_set(self, ws=None, t1=0.8) -> SupportSet               # 每实例一个事件；多段 hits > 1
    def targets(self, tk) -> list[Target]                              # 每个活敌的受击框均值路径 + 投射物
    known: bool                                                        # 全部在场类型都已认证（§4.4）

# combat/terminal.py（新）
class EnemyFields:                        # 每个敌人一张位图 [cells, bins]，按固定计划轮转
    def update_slice(self, mf: MultiForecast, frame: int) -> None        # 每帧 ≤ 1 个敌人；事件时优先
    def eval_rows(self, end_states) -> tuple[E, trapped, overlap, O, K, H_exp]

# combat/tactics/gauntlet.py（新）：L2
class GauntletTactics:
    def decide(self, ws, mf, fields, wave, sup_decision, h) -> GoalPrefs   # 10 Hz + 事件，分片
@dataclass
class GoalPrefs(TacticPrefs):             # Bell Beast 只用旧字段
    goal: str = "LOCAL"; target: int | None = None
    region: tuple[float, float, float, float, str] | None = None        # x0, x1, y0, y1, contact
    hit_w: dict[int, float] = field(default_factory=dict)
    vocab: frozenset[str] = frozenset()                                 # 额外宏：CLIMB_POCKET、DASH_TO、COGFLY
    ttl_s: float = 0.6
```

`PlannerConfig` 新字段：`two_stage`、`K_b`（96–128）、`deadline_ms`（约 11）、`hitfx_k`（32）、`clash_k`（16）、`T`（Forum 默认 36，见 4.5）、`variants = "bounds_lo"`（Forum；Bell Beast 改不改另行 A/B）。

### 4.4 安全：不变的、新增的检验

1. **支撑认证**（R2 的硬门槛）：每类留出召回 100 %（滞后 2 / 3 / 4 帧，按场分折，与 Bell Beast 的 23,896 / 23,896 同口径），用不上余量就加"每类、每家族的留出残差 p99.9"作余量，召回 100 % 后 `known = True`。做不到的家族用结构性并集（例：Clawmaiden 瞬移用 Teleplane 区域 x 17.42–45.94、y 7.35–13.26 的并集）。**未认证之前只跑数据，不跑评估**（§1 第 4 条）。
2. **核心躲避集**（约 48 行：WAIT、MOVE、JUMP 3 档 × 3 向、DASH、在墙上时贴住 / 松墙 / 蹬墙跳 / 爬墙，各配 3–4 种续段）每帧都在；通过阶段 1 的核心行一定进阶段 2。属性测试：任意 GoalPrefs / 权重下，核心行的 S / Hz / U 逐位相同；有目标时 FORCED_RISK ⇒ 默认目标下也 FORCED_RISK。
3. **选中的计划永远做过包络检查**：截止时间只在"已检查的块里已经有 S = 0 的行"时生效；没有就继续检查直到找到或全部检查完（这时可能超时，单独计数，不叫 FORCED_RISK）。V 只在做过包络的行上算，所以阶段 2 带上前几名的兄弟。
4. **L2 失效 → LOCAL**：注入 10 % / 100 % 失败，100 % 时整个决策（选中计划、FORCED_RISK、监督器触发）与无 L2 时逐位相同。
5. **场只进打分**：属性测试"场空 ⇒ 细查询空"在留出录像上随机 10⁵ 个（格、时间）0 违反（按 §1 第 10 条做时间膨胀）。
6. **一致性**：击杀、打铃、拼刀弹开之后主角周围 1 s 内的危险区不得大于不做（录像 + 模拟），违反 = 模型错误。
7. **监督器**：`worst_known_damage = 2`（Forum）；多段事件 `hits` 与 `damage` 用录像里实测的最大整链（`multi_hit_follow_ups`）；Q4 按实例计；YELLOW 的"不打可能致死的一击"按每个敌人的 hp_est 和该类实测击杀冻结时长；P1 的安全窗口 = 波间安静段。
8. **视觉合法性**：§4.6 的表 + ObservabilityFilter 单元测试扩到 9 类 + 每轮一小批 degraded_dust 回归（M2.md 10-03 的决定：保留纪律、暂停精调）。

### 4.5 算力预算（训练负载、4 线程）

| 阶段 | Bell Beast 今天（表 A） | Forum 合成方案估计 p50 / p99 | 依据 |
|---|---|---|---|
| 预测（K = 2–4，walk 缓存） | 0.16 / 0.62 | 0.5 / 2.0 | 按敌人数线性；walk 只在状态变化时重走 |
| 场（每帧 1 个敌人）+ L2 | 战术 0.41 / 3.82 | 0.8 / 2.5 | 表 D：一个敌人 0.36 / 1.37；L2 目标是查表 |
| 推演：标称 ≈ 400 × 36 + bounds_lo ≤ 128 × 36 | 2.84 / 4.30 | 3.2 / 6.0 | 表 B：1.76 / 3.70 + 1.44 / 3.59（p99 不全叠加） |
| 支撑：中心点 + 包络点 + 舒适度 + 锁定 / 尾部 | 2.09 / 10.56（含命中重推） | 1.9 / 4.5 | 表 E：一个 SupportQuery、400 行中心点 ≈ 1 ms |
| 命中效果（前 32 行、K_eff ≤ 3） | 0.17 / 7.42 | 0.3 / 2.5 | 加上限 |
| 打分（多目标 + 终点价值查表） | 0.15 / 2.9 | 0.5 / 2.5 | |
| 过滤 + 选择 | 0.6 / 3.8 | 0.6 / 3.5 | 不变 |
| **合计** | 6.72 / 20.4 | **≈ 8 / 15–17**（截止时间后 13–15） | p99 不是各项相加 |

- 视野：Forum 默认 T = 36（0.6 s），0.6–3 s 交给终点价值和尾部检查，长招仍用自适应视野延长；T = 48 是 R5 的 A/B 组（看 FORCED_RISK 和受击）。Bell Beast 不变。
- 正式运行只有一个游戏实例，规划器可以给 8 个 P 核线程；之后到 3–4 ms 的路线（不阻塞 M2）：推演与支撑查询融合成一个核（边推边查，接触即停，不物化包络）、核心集与族按局面再剪、L2 改 `nogil` 放 E 核（H §11.4）。

### 4.6 视觉合法性（新组件读什么）

| 组件 | oracle 视图（开发、评估） | 视觉视图（M3）的来源 | 现在就守的纪律 |
|---|---|---|---|
| EnemyTracker | FSM 状态与 StateTime（同 Bell Beast 的 oracle 视图） | 每类可观测阶段表 + 阶段内时间 | 跟踪器按视图分支，规划器 / L2 只看 MultiForecast |
| 敌人身份 | iid | 检测轨迹 id | 不跨轨迹用 iid |
| 敌人 HP（击杀价值、U、YELLOW） | **不读 `ents.hp`** | 数看到的命中 | 两种视图都用 hp_est |
| 波次 | **不读 `room.battles`**（只作测试真值） | 静态波次表 + 看到的死亡 / 出场 | WaveTracker 与 `room.battles` 比对只在测试里 |
| 投射物 | 实体位置 | 检测轨迹（同 `bell_track`） | 速度用轨迹拟合，不用导出速度 |
| 可拼层 / 反击 | 静态表（离线由 parry 位建） | 静态表；成败看闪光和画面静止 | 运行时不读 parry 位、不读 `damage_blocked` |
| 助战、Cogfly | `allies` 导出的位置 | 检测 | 不读它们的 FSM |
| 画面外入场 | 静态出生点 + 入场模板 | 同左，起始时间按"上次在画面内"放宽 | 不读 Clapper 落下前的 `Rest` |
| Slam Range 是否触发 | — | 几何推断（只认主角物理碰撞盒，forum.md §10.2） | 不读 FSM 的 range 状态 |

---

## 5. 实施计划（按轮，每轮是一批代理工作）

**顺序调整（2026-10-05，你看了 A0 后的提议）**：A0 的 87 % FORCED_RISK 主要来自待机小怪可拼招的支撑；除 Clapper 外小怪的招几乎都可拼，所以**拼刀（R8）提前到 R5 之后、R6 之前**：拼刀分支（成功 = 0.15 s 无敌 + 按方向后坐 + 冷却清零；失败 = 挨打）按实测成功率进风险，成功率高的招不再逼出 FORCED_RISK；例外照旧要躲：所有本体（Tiny 冲撞最多）、Clawmaiden 的矛和矛爆炸、Bellbearer 的钟（只能打改向）、Clapper 全部；同一判定连拼的间隔 = 0.1 s 冷却清零 + 我方起刀到生效（Reaper 约 0.083 s）≈ 0.18 s > 0.15 s 无敌，长时间判定（如 Minister 冲刺路径）要靠后坐出判定或换段才不吃那约 0.03 s 的空档；一刀只盖一侧。Clapper 单独做绕后控制器（R6 的目标 + R7 场景测试）。新顺序：R5 → R8 → R6 → R7 → R9 → R10。**你 10-05 的补充（并入 R5 / R8 / R6）**：(1) 拼刀成功后 0.15 s 的 `parryInvulnTimer` 挡所有 ENEMY 伤害（`HeroController.cs:5391`），所以左右同时来的两刀拼到一边、另一边在 0.15 s 内到的就被吃掉；两刀的间隔由支撑里各招的命中时刻给出。(2) 拼刀为主的打法用出刀快的纹章（Wanderer 冷却 0.3 s / Hunter 0.41 s，不用 Reaper 0.5 s），R8 实验默认 Wanderer。(3) Reed 三连刺的刀可拼，但扑过来的本体不可拼，倾向躲；Tiny 能不能打退（冲撞中被打是否停下）要查 hero_caused / 实测；Bellbearer 正下方几乎打不到（R1：正下方 37.5 s 0 次，附近 4.75 次 / 分），但正下方在它的闪避框里（x ±3.3、y ±6.66），一进去它就闪走（每次约 0.97）；Clawmaiden 的矛放一侧、人到另一侧；飞行怪下方对 Reed 无效（R1：3.5 vs 3.1 次 / 分）。(4) **R6 v0 用你的规则，和 R5 同一轮先做**：有落单的就冲上去剁；都分散时先打跑得快、先追上来的；没有落单的就在远处游走，等快的先追过来再打（按速度把它们拉开）；R5 的终点价值负责游走和冲上去时不被堵死。**优先级（你 10-05）**：Clawmaiden 最先打（下方也不安全，但它会吸丝、吸满就放大标枪，爆炸 r 3.55、2 格）；Minister 最后打（会俯冲，下方不安全）。Clawmaiden FSM（场景包）：`Spin Antic` 时主角丝 < 2 → 取消、丝 < 3 且 Might Slash → 改斩；`Spin 0 → 1 → 2` 每段一次 SUCK TICK 吸丝，中途主角没丝（NO SILK）→ `Silk Break`、不放矛；吸满三段 → `Spin End → Spear Cast Antic → Spear Fire`。所以打断它的吸丝 / 让它吸不满就没有大标枪；**Minister 格挡（你 10-05）**：格挡时站在它面前等、别碰它本体（格挡姿态的本体 678 次接触），姿态结束那一帧开砍：`Parry Stance Antic` 0.13 s → `Parry Stance` 约 0.87 s（没被砍时）→ `Parry Stance End` 0.25 s（可砍）→ `Evade?`（你在它闪避圈 r 4.96 里时一半概率闪走）→ `Retreat?` → `Set Attack Time`（0.5–1.5 s 后才出下一招）；R6 的诱招 / 惩罚窗口按这个时序。（你 10-05 追问：`Parry Stance End` 里不闪、挨打也不打断（不在 hero_caused 的出边里），结束后才决定闪，闪避前摇 0.1 s 后才动，所以收招开始约 0.35 s 内它不会移开；我方刀生效：Hunter 第 0 帧起（0–0.1 s）、Reaper 0.083 s、Wanderer 未提取（R7 实测补）；收招期间出刀必中，没闪就继续砍，但追击中挨打会把它的攻击计时夹到 ≤ 0.5 s）**收招时放飞针（你 10-05，R7 场景）**：在它闪避圈（r 4.96）外 5–10 u 放，针要在 `Parry Stance End` 里命中（命中在按键后约 0.15–0.3 s；姿态时长约 0.87 s 很稳，oracle 有状态计时）；早了打在格挡上 → BLOCKED HIT → 4 段反击；人在圈外它收招时不会闪，飞针两下（2 级针 6 + 6，耗 1 丝、第二下回 1 丝）；被打后 `Retreat?` 的 TOOK DAMAGE 把攻击计时夹到 ≤ 0.5 s，而飞针结束的弹起没有无敌，要规划落地后躲它的冲刺。`Rest` 醒来时主角丝为 0 会回去睡（`Silk? → Silkless → Rest`，只有挨打才醒）。

依赖：R0 ∥ R1 → R2 → R3 → R4 → R5 → R6 → R8 / R9 → R10；R7 在 R1 的数据到了之后与 R4–R6 并行。每轮结束合并前跑全套测试和 Bell Beast 回归（Forum 开关关时逐位相同 + 每轮 50 场 oracle 小批 ≥ 97 % CLEAR、0 WOULD_DIE）。

| 轮 | 内容 | 产出 | 验收 |
|---|---|---|---|
| **R0 离线：表与工具**（1–2 个代理，无游戏） | `behaviour_build --encounter Forum` 用全部 128 场重建；`support_recall --encounter Forum`（按实例配对、L = 2 / 3 / 4、oracle 与 ve 两种视图、按场分折）；数据产品：每类多段整链的最大 hits / 伤害、死亡尾巴帧数、击杀冻结时长、"待机 → 最快一击"的时间 / 距离分布（按距离档）、惩罚窗口表 Pun_a、波间安静段（本波最后一击 → 下一波第一次可能接触）、Garmond 的目标选择统计；把 H 的 `forum_sim` 和 I 的 `forum_simul` 合成 `tools/forum_simul.py`；`planner_bench --encounter Forum` 的回放脚手架 | 表、工具、forum.md 新节 | 每类留出 anchor > 0.5 u 的比例和需要的余量有报告；数据产品有单元测试和复现命令；`forum_simul` 复现 H 表 1.2 的数字 |
| **R1 游戏内：探针与定点数据**（1 个代理，2–3 个实例，与 R0 / R2 并行） | ① 波次课程的机制：DebugMod 战斗中读档到底恢复什么；训练 mod 命令"从第 i 波开始"（`BattleScene.StartWave(i)` 或"前面波次一击死"快进），二选一；② 贴墙 Bind（能否、会不会脱墙、Bind 期间受伤盒）；③ 墙砍真实够距；④ 数据策略 v2：冲刺 / 冲刺斩 / 飞针近身、跳到 Envoy 上方、定点对着可拼层出刀（拼刀成败标签）；⑤ Envoy 定点存档；⑥ fo_C（无助战）20 场；⑦ 部署 `slash.dump paths`（冲刺斩多边形）、飞针 FSM 转储与激励录像、Cogfly 投掷硬直 | facts 条目 + 录像 | 每项一条 facts 结论（含【未核实】的转为实测或明确否定）；v2 数据每类闪避 / 反击招 ≥ 200（Envoy 和入场除外） |
| **R2 多敌预测**（1–2 个代理，离线） | `EnemyTracker`；把 walk / place 中与 Boss 无关的部分抽成函数；`MultiForecaster / MultiForecast`；一个装 9 类的 `SupportQuery`；walk 缓存；死亡尾巴；入场模板（WaveTracker 给区间）；确定路径投射物；Tiny 合群放置（≥ 3 只时）；`support_set`（每实例、多段 hits > 1） | 代码 + 单元测试 | (a) 包住单个 Bell Beast `Forecaster` 逐位相同；(b) 128 场按场分折，9 类留出召回 100 %（L = 2 / 3 / 4，oracle；ve 视图用占位滤镜跑一次）→ `known = True`；(c) 投射物轨迹中心误差 p99 ≤ 0.3 u；(d) 第 6 波回放 `forecast(2 s)` p99 ≤ 3 ms；(e) 每进程内存实测 ≤ 1.5 GB |
| **R3 快层：Forum 词汇与算力**（1–2 个代理，离线） | 冲刺两处修正（kin_check dash ≥ 99 %）；姿态族 + 核心躲避集；Reaper 攻击形状进 `_score_kernel`（含墙砍）；K 目标打分与命中效果（上限 32 行）；两段式 + 截止时间；Forum 用 bounds_lo；U / I3 移植（最后一个波次成员）；YELLOW 的每敌击杀冻结；监督器数据来源（多段事件、`worst_known_damage = 2`、Q4 按实例）；**负重环带上下文**（路线 S09 起装着；资产值 i-frame ×1.3 = 1.0 → 1.3 s、受击击退 ×0.5、钉子后坐 4 步、上砍 RecoilDown 减半、最大下落 38；`HeroParams.with_weighted()` 已有但 bot 录像里从没装过，Forum 评估前用装着它的录像核对，监督器的受击后窗口按 1.3 s 算）；**受击反应分支**（forum_reactive_moves.md）：命中效果分支加上敌方的受击反应——Clapper `Idle` 被打 → `Dmg Attack`（闪避概率随被打时刻变）、Reed 被打转刺、Minister 攻击计时夹到 ≤ 0.5 s、Maestro → `Summon?`、Envoy 走路时被打 → 冲锋；**落地清后摇**（你 10-04 问；`HeroController.BackOnGround` 10286-10290：落地时这一刀已不在出刀 / 起刀中 → `ResetAttacks`，attacking = false，后摇锁（转身、冲刺、Bind、丝技、飞针等的 AttackRecoveryTime 门）立即解除；攻击冷却不变）：kin_jit 落地时没有清 ATTACKING，Reaper（后摇 0.3 s、刀在约 0.21 s 收）在 0.21–0.3 s 落地时模型比游戏多锁最多约 0.09 s；Hunter 0.15 / Wanderer 0.1 不受影响。补上并用 kin_check 核对 | 代码 + 属性测试 | §4.4 第 2、3 条属性测试；Bell Beast 逐位 + 50 场小批；Forum 开环 bench（三组录像：Maestro 波、混合波、终局）p50 ≤ 9 ms、p99 不高于同负载下 Bell Beast bench（约 20 ms）；被选中计划 100 % 做过包络检查（审计计数） |
| **R4 A0 基线实战**（1 个代理，4 实例） | LOCAL 多敌战术（EVADE / HOLD / ENGAGE 最近 + 类型优先级）+ WaveTracker + `Forum.yaml` v0（优先级、口袋两条否决、Cogfly 默认、防御姿态不近战）；50 场完整连战 fo_A，oracle | 基线报告 | 框架、记账、决策日志正常；WaveTracker 与 `room.battles` 100 % 一致；**支撑外命中 0**（否则回 R2）；记下 A0 的全部指标（§6.3） |
| **R5 终点价值**（1 个代理，离线 + A/B） | 场（轮转、时间膨胀）、可达模板、E / trapped / 重叠 / 击杀价值 / H_exp 进 J；T 36 vs 48；**先做：决策的感知时刻**（你 10-04 问"出招概率和距离用的是哪一刻的距离"）：行为表现在取的是 Control FSM 离开决策状态那一帧（多数怪 = 前摇开始那帧）；但有的怪更早就读了主角位置（范围触发器发事件、更早状态里量距离存进变量、再随机等待才分支），那时的距离才是驱动量。从 FSM 静态找出每个决策状态读主角位置的动作和所在状态，在那一刻取协变量；在留出录像上比较分支帧 / 感知时刻 / 固定提前 0.1–0.5 s 的对数损失，选最好的；诱招（O、BAIT）用它。只影响概率和打分，支撑不变；**同时：FSM 里的冷却**（你 10-04 问"状态机里有没有技能 CD"）：STATE 只逐帧导出当前状态、状态内时间和转移事件，不导出 FSM 变量；冷却在 FSM 里是 bool 变量 + 定时动作 + 随机选择动作的防重复计数（例：Bellbearer `In Range` 每帧测 `In Evade Range && !Wall Behind && Can Evade && !Evade Cooldown` → EVADE；`Can Evade` 进状态 0.5 s 后才为真，`Evade` 置 `Evade Cooldown`，只有下一次 `Throw Antic` 清掉：闪过一次后，扔钟之前不会再闪）。从场景包静态抽出每类的冷却逻辑，换成视觉可得的历史条件（上一招、状态内时间）进行为表；能确定且可观测的冷却可以收紧支撑（要重新认证），否则只进概率；**按分支分别统计**（你 10-04：防御被打 → 反击 和 姿态自然结束 两支可能 CD 不同）：上一招的分支和"最近被主角打中"（Minister `Chase` 被打把攻击计时夹到 ≤ 0.5 s）作历史条件，两支到下一次出招的时间分别统计（forum.md §11 防御姿态一节）；**身体触发的反应分支**（forum_reactive_moves.md，你 10-04 说"闪身由大黄蜂动作决定"：由主角**物理碰撞盒**进入第 13 层 AlertRange 触发，与按键 / 出刀无关）：`reactive_triggers.json`（每类触发盒几何、门控与 50 % 硬币、冷却）+ EnemyTracker 跟踪门控；候选的身体路径在门开时进盒 → 下一帧以每次进入的概率 p 进闪避（Bellbearer ≈ 0.97、Clapper ≈ 0.49、Reed 防御 ≈ 0.45、Reed 闪避 ≈ 0.8–0.95），只进 J / P，不进 S；行为表不加"主角动作"协变量（留出无增益），改用触发盒几何 + "刚被打中" | 代码 + A/B | §4.4 第 5 条 0 违反；场每帧 p99 ≤ 2 ms；对 A0 的成对 A/B（课程或完整连战）：每波受击、FORCED_RISK / min、Q3 退出都下降，0 WOULD_DIE |
| **R6 L2 目标层**（1 个代理） | `GauntletTactics` + GoalArbiter：ENGAGE / FOCUS / BAIT / SPLIT / POSITION / PRE_WAVE / POCKET / HEAL / COGFLY / LOCAL；O（惩罚窗口 × 行为表概率）；Q1a 安全点；Q6 攒丝；终局最后一击的 HEAL 优先；被挡回报 | 代码 + A/B | §4.4 第 4 条注入测试；目标切换 ≤ 10 / min；每秒按键数和计划改动率不高于 A0；对 R5 的成对 A/B：敌人在承诺招里的时间占比、DPS 上升，受击不上升；**远处目标场景测试**（你 10-04 的担心：两只怪相距超过 0.6 s 的跑动距离时，规划器视野里看不到"转头去打另一只"）：录像切片 + 合成局面，近处一只待机、远处一只在长招后摇（剩余惩罚窗口 > 跑过去的时间，冲刺 + sprint 约 17.5 u/s），L2 必须选远处那只并在窗口内出刀；反过来窗口不够时不能去；目标仲裁日志逐条可查 |
| **R7 新原语**（1 个代理，离线，R1 数据到后与 R4–R6 并行） | `M_DASH_STAB`、`M_HARPOON`；冲刺斩 / 飞针多边形；`CLIMB_POCKET` 宏；DASH_TO / CLAWLINE_TO 宏；**锯齿环与滑翔取消**（clawline_glide_combo.md）：`glide_spike` 攻击槽（多边形、L / R 生效窗口、每只敌人一次、0.1 s 后 1 点、8 ×（1 + 0.6 × 制作匣）× 等级、同一时间一圈的 0.39 s 锁定）；kin_jit 的滑翔攻击取消改为无条件出刀（游戏里跳过攻击冷却）；`combo_probe.py` 先跑（saw / bypass / lockout / claw / rprlock）；K1 A/B 锯齿环 vs 护佑钟；**飞针各阶段能否出刀 / 拼刀**（你 10-04 问弹起阶段能不能拼）：读码结论——投掷 / 冲刺 / Catch 期间 FSM 夺控，不能出刀、不能拼；`Bounce Up` 交还控制后 `DownspikeBounce(harpoonRecoil)` 弹起阶段 `CanAttackAction` 成立（只看上一刀的攻击冷却），横砍 / 上挑可以出、可以拼，弹起本身无无敌；combo_probe 的 claw 实验加测"弹起后最早出刀帧"；**场景测试：Clapper 施法窗口放锯齿环**（你 10-04：双手举起往地上放一排小符文那招原地站很久、只打地面，在它面前放锯齿环正合适）：CC_CAST = `Spell Antic` 0.73 s + `Cast 1` 0.10 s + `Cast 2` 0.42 s ≈ 1.25 s 原地不动（ChoirClapper.json dwell，n 3,482），之后 rune bomb 一对一对向外炸（±4.2 k u，r 2.17，中心 y 3.67、顶约 5.84，亮 5–7 帧）；R2 的确定路径投射物给每个 x 的爆炸时刻，规划器应自己选"在它面前小跳开披风、本地符文亮时人在空中"；验收：录像切片 + 合成局面里，CC_CAST 窗口的平均伤害 ≥ 站着躲开的方案，0 次被符文 / 本体打中；注意：施法状态（`Spell Antic` / `Cast 1` / `Cast 2`）没有 TOOK DAMAGE 出边，挨打不打断；回到 `Idle` 后挨打 → `Dmg Attack`（中位 0.3 s，hero_caused.json），所以窗口按施法 1.25 s 算，`Idle` 里贪刀要计入受击反击；**另一个场景（你 10-04）：Clapper 两个跳的招（CC_JUMP 跳砸、CC_JUMP_CAST 跳起施法）可以钻到它身后追着打**：起跳前摇约 0.48 s、空中约 0.9 s、落地 `Slam 2` 约 0.07 s + `Slam Recover` 约 0.23 s；验收：起跳后从它下面穿到落点背后、落地后在背后出刀，0 次被砸地 / 本体打中；跳起施法的 `rune slam`（r 7.19，落地后约 2 s 出现、再 1.28 s 炸）炸之前离开圆；与 `clapper_face.md` 的面前 / 背后安全区核对；**冲锤时踩头跳过**（你 10-04）：`Slam Antic` 0.8 s 前摇里下劈踩它头（本体顶约 y 7.0，下劈命中有 0.16 s 对敌人无敌），弹起约 +4.7 u、0.41 s 到顶，脚底约 11.7 > 锤判定顶 10.58，要在锤的生效帧（承诺后约 0.87–1.03 s）时人在弧线高处或已越过它的 x 范围；落到背后打 `Slam Recover`；平跳不踩头脚底只到约 8，挡不住锤，由支撑检查定；从下面穿过时顺手上挑、包括小跳上挑（你 10-04）：跳的过程中挨打不打断它（`Air` / `Jump` 没有 TOOK DAMAGE 出边），上挑够得着它本体下沿、而主角受伤盒碰不到本体（2 格接触伤害）的那段弧线才出刀（R1 实测起跳最高 8.219 u、空中 0.917 s），由支撑检查决定；你在半速下感觉"至少 2 s"= 游戏时间 1.25 s（半速实时 2.5 s）+ `Idle` 停留（中位 0.3 s）+ 符文还在炸（tail p50 2.1 s）；**小跳平砍是否更快**（你 10-04 转述 YouTube）：读码——普通出刀冷却 `DidAttack` = 纹章的 AttackCooldownTime（Hunter 0.41 / Reaper 0.5 / Wanderer 0.3 s），空中地面相同；缩短冷却的只有：下劈命中弹起 0.15 s（`SetStartWithDownSpikeBounce`）、冲刺斩命中弹起 0.1–0.15 s、拼刀清零、滑翔攻击取消跳过冷却（但滑翔要等这一刀的攻击锁结束，横砍上算不出更快）；combo_probe 加一项：各纹章站着连砍 vs 小跳连砍 vs 下劈命中接横砍的出刀间隔实测；数据策略 DASH_IN 修正（冲刺键按住 ≥ 0.25 s、冲刺后 0.1 s 再按攻击，R1 里 0 次冲刺斩）后再采 R7 数据；`probe_dash_stab.py`（未跑）确认你看到的"往前闪"是哪一招 | 运动学 + 候选 | 留出包络覆盖 ≥ 99 %（与 movement_kinematics 同口径）；多边形命中核对 TP / FP 同 Reaper 横砍；爬墙宏离线 ≥ 95 %、实战 ≥ 90 %；A/B：DPS 和每波用时改善、受击不上升 |
| **R8 拼刀**（1 个代理） | 可拼层模板、`EV_CLASH` 两分支（上限 16 行）、成功率（类型 × 招 × 视图）、一致性检查；**连招里的出刀也是拼刀候选**（你 10-04：飞针-滑翔-下劈-滑翔连招中间的攻击可以拼刀，按怪的前摇调节奏）：空中横砍 / 下劈碰到 canClashTink 的碰撞体同样触发 NailClash，EV_CLASH 分支对空中行同样展开，节奏由前摇时刻和连招的取消窗口（clawline_glide_combo.md）决定；**成功分支更正**（反编译，forum.md 拼刀效果一节）：不是"撤掉该招余下模板"，而是主角 0.15 s 对所有敌人伤害无敌 + 冻结 + 按方向后坐（下劈拼刀弹起）+ 0.1 s 后攻击冷却清零；只有 FSM 接 `PARRIED` 的招被打断（Forum：Envoy 冲锋 → Deflect、Reed 防御反击 → Multihit Clashed），其余照常打完，所以成功分支要用后坐后的位置对剩下的模板做支撑检查；**多段连拼**（你 10-04：多段攻击 / 多段反击是不是原地一刀一刀拼）：Forum 的多段招每段是单独的可拼碰撞体（Minister `ParrySlash Hit 1–4`、冲刺 `Slash Collider`，Choristor `Whip Hit 1–6`，Clawmaiden `Slash Collider 1–4`，Reed `ParrySlash Hit` 拼一下整套取消），所以推演按段展开拼刀分支（每段成功：0.15 s 无敌 + 后坐位置；失败：被钩住整条连段）；测每招"整条连拼"的成功率，与"拼第一段后借后坐脱身"比；负重环带缩短后坐，可能更容易连拼，A/B 时带上；**出刀方向决定后坐**（你 10-04；`DamageHero.NailClash` 按我方攻击的 direction 分支）：横砍 → 水平后坐 `RECOIL_HOR_VELOCITY` 3.75 u/s × 8 步 ≈ 0.6 u（负重环带 4 步 ≈ 0.3 u），上挑 → 无水平后坐、只截断上升（负重环带减半），下劈 → 弹起；敌方碰撞体带 `noClashFreeze` 时无后坐无冻结。分支按所选攻击的方向放后坐；候选里同一段同时试横砍 / 上挑 / 下劈（够得着才算） | 代码 + 剧本条目 | 一致性 0 违反；整场 A/B（每组 ≥ 200 个起点，按类型 × 招分组）：开的一组受击和退出不更多才写进 `Forum.yaml` |
| **R9 风险回归与权重**（可选） | r̂（在规划器自己的 R4–R6 录像上拟合，随机策略数据只作初值）；权重在课程批次上做 CMA-ES / 贝叶斯优化；两步目标 ALTERNATE（只在 `forced_audit` 显示"A 放长招时本可打 B"的机会被大量错过时） | 拟合 + A/B | r̂ 留出 AUC ≥ 0.75、校准误差 ≤ 0.05；权重在留出批次上不退化 |
| **R10 门槛与 K1** | 完整连战（oracle，fo_A，当时 A/B 胜出的配置）序贯贝叶斯门槛；degraded_dust 小批（纪律回归）；fo_C 后备组；K1 纹章 A/B 输入 | 门槛报告 | CLEAR ≥ 70 %、WOULD_DIE 上界 ≤ 1 %（0 次时需要约 300 场）；实战每场 tick p99 中位数 ≤ 15 ms、迟到跳帧中位数 ≤ 10（若你定了口径） |

---

## 6. A/B 评估方案

### 6.1 协议

1. **开发期**：若 R1 找到可靠的"从第 i 波开始"，按波次组合分组（混合波 0 / 2–3 / 8 / 9 / 11、Minister 波 4、Clawmaiden 波 5 / 10、Maestro 波 6 / 12、Clapper 波 7 / 13），每组随机化主角位置 / HP / 丝，开发 ≥ 50 个起点、A/B ≥ 100 个起点 / 组 / 臂；否则用完整连战、按波统计。
2. **成对种子**：同一组种子（`randomize_start` 的 AI 随机数、HP、位置）在各臂之间共用，比较配对差（H §14.1）。
3. **门槛只用完整连战**（DESIGN §3.9.3：阶段存档只用于练习）：oracle 视图、fo_A、时间盒 1500 s；序贯贝叶斯（同 Bell Beast 的 `bayes_gate`）；WOULD_DIE ≤ 1 % 在 0 次时约需 300 场（3 / n 法则；Beta(1, 1) 后验 95 % 上界同量级）；规划器一场约 8–14 min，4 实例约 12–18 h。
4. **纪律**：每轮一小批 degraded_dust 回归（不在模拟视觉上精调）。

### 6.2 臂

| 组 | 比较 | 主指标 |
|---|---|---|
| 终点价值 | A0 / + E / + E + trapped / + H_exp / + 击杀价值 | 每波受击、FORCED_RISK / min、Q3 退出 |
| trapped 的位置 | J 里大权重 / 字典序新一级（V 之后、P 之前） | 同上 + 按键经济（新一级要你同意，§9） |
| 视野 | Forum T 36 / 48 | FORCED_RISK、受击、tick p99 |
| L2 | 无（LOCAL）/ 有 / 有 − O / 有 − SPLIT | 敌人在承诺招里的占比、DPS、每波用时、受击 |
| 新原语 | 无冲刺斩与飞针 / 有 | DPS、每波用时、受击 |
| 拼刀 | 关 / 开（类型 × 招分组） | 受击、WOULD_DIE 上界、退出、用时 |
| 终局 | 口袋 / 地面 | 终局受击、终局用时 |
| Cogfly | 第 6 波 2 次 + 终局 2 次 / 全留终局 / 按需 | 用时 |
| 助战 | fo_A / fo_C | 全程（K1 输入） |
| 纹章 | Reaper + 爬墙爪（fo_A）/ Hunter_v2（fo_B） | K1 纹章 A/B |

### 6.3 指标

- **结果**：CLEAR、QUIT（按 Q1 / Q1a 失败 / Q3 / Q4 / Q6）、WOULD_DIE（含最后一击后 4.1 s）、STUCK、整场和每波用时。
- **安全过程**：每波受击、damage_blocked、FORCED_RISK（tick 比例和每分钟段数；超时型单独计）、未预测命中（按实例）、风险档时间、Q3 次数与触发的敌人类型。
- **打法**：敌人在承诺招里的时间占比、主角命中落在承诺招里的比例、DPS（钉子 / 丝矛 / Garmond / Cogfly 分开）、击杀来源、Clawmaiden 偷丝次数、Bind 次数和成功率、"受击后 2 s 内有够回血的窗口但丝不够"的次数。
- **分层健康**：目标切换 / min、目标失效 / 过期 / 被挡、LOCAL 占比、场违反数（必须 0）、tick p50 / p99、迟到跳帧。
- **按键经济**：每秒按键数、按键提前量分布、计划改动率、同帧抖动（与你的录像对比，如有）。
- **事后审计**：每次 FORCED_RISK 往前 1–3 s 重放所有候选与目标，统计"当时有没有能避免它的站位 / 目标"（DESIGN §3.5.7 的验收）；每次受击的 postmortem；`opportunity_audit` 的 Forum 版（本能打中却没打、本能打铃 / 拼刀却没做）。

---

## 7. 主要风险

| # | 风险 | 后果 | 对策 |
|---|---|---|---|
| 1 | 支撑认证不了（留出 0.3–5.2 % 在 0.5 u 外，Clawmaiden、Reed 最差） | 全程 YELLOW、h = 2 即 Q3；或未预测命中 | R0 用 128 场重建；按类按家族的余量；结构性并集；R2 的召回 100 % 是硬门槛；R4 支撑外命中 0 |
| 2 | 多个待机敌人的支撑并集太宽 → FORCED_RISK 多 → 不敢出刀、攒不到丝 | CLEAR 低、用时长 | 确定路径投射物；终点价值把主角带离被夹的位置；SPLIT；之后才考虑 DESIGN §3.5.3 的"可反应"放宽（需要视觉前兆时长，M3） |
| 3 | Q3 退出过多（多段攻击到处都有） | QUIT 吃掉 CLEAR | H_exp 项；HEAL 优先；按 Q 统计 QUIT；§9 第 2 个决定 |
| 4 | 算力（Forum 推演 2.3–2.6 倍、多目标） | 迟到、反应慢 | 两段式、上限、截止时间、T 36；R3 有量化验收；不够时做融合核 |
| 5 | L2 与规划器打架（目标拉、安全推） | 抖动、按键浪费 | 被挡禁忌、滞回、寿命；目标只进 J；`goal_audit` 指标 |
| 6 | 新原语模型不准（冲刺 97.34 %、冲刺斩 / 飞针未建） | 误判 | 修两处已知错误；≥ 99 % 前不进候选 |
| 7 | 口袋漏洞（贴墙起跳，最近 0.87 u）；贴墙 Bind 未知 | 终局受击；回血点不可用 | 两条规则作有效条件和否决；R1 实测贴墙 Bind；口袋 A/B |
| 8 | 最后一击（I3）与 Garmond 抢最后一刀 | 终局卡住或违反 I3 | U 移植；终局先回满血；低血时远离 |
| 9 | 拼刀成功率在 oracle 偏高 | 视觉下更差 | 按视图实测；整场 A/B 赢了才开 |
| 10 | 助战改变敌人行为；后备组（fo_C）支撑不全 | 后备组未预测命中 | fo_C 20 场单独留出核对，不过就单独建表 |
| 11 | 评估太慢（一场 12–16 min），波次课程机制可能不存在 | 迭代慢 | R1 探针；成对种子；门槛只跑完整连战 |
| 12 | 内存（9 类 × 4 实例 + 舒适度 + 场模板） | 实例 OOM | 实测 384 MB / 进程（13 场的表）；R2 验收 ≤ 1.5 GB / 进程 |
| 13 | 视觉合法性泄漏 | 最终路径失效 | §4.6 的表、滤镜测试、degraded_dust 回归批 |

---

## 8. 需要你回答的问题（游戏经验，只有你知道）

1. **多段攻击**：Choristor（圣咏使徒）的鞭、Reed（簧片战士）的连刺 / 招架反击、Minister（圣咏大臣）的连斩，被连上一次一般掉几格？能不能中途脱出（冲刺、跳）？——决定 Q3 在 Forum 怎么用（§9 第 2 条）。
2. **防御姿态**：Minister 的 Parry Stance、Reed 的 Defend，打上去会被反击吗？反击能躲 / 能拼吗？你遇到时怎么做？
3. **拼刀**：Forum 里哪些招"近身难躲又出得频繁"、你常拼？哪些你从来不拼？（白名单和 R8 A/B 分组的先验）
4. **冲刺斩和飞针**：在 Forum 里分别用在谁身上？飞针钩中敌人后会把你拉到它身上吗（会不会撞上身体伤害）？只有"冲刺 + 普通攻击"够不够近身？（决定 R7 是否提前到 R5 之前）
5. **贴墙 Bind**：装了爬墙爪贴在墙上能不能 Bind？会不会掉下来？你在口袋里回血吗？
6. **终局**：最后一只 Clapper 死时的慢动作期间你挨过打吗？最后一只低血时你会先回满血再补刀吗？Garmond 抢最后一击常见吗？
7. **Garmond**：他一般追谁（最近的？最强的？）？你会不会故意把怪引到他身边，让他接一只、你打另一只？
8. **Cogfly**：你在哪几波放、一次放几只、能撑多久？
9. **波前站位**：每波开打前你站在哪？特别是 Clawmaiden 从左上飞进的第 3 / 5 / 10 波（索引）、两只 Maestro 的第 6 波、Clapper 落下的第 7 / 13 波。
10. **先杀顺序**：Clawmaiden > Maestro（召唤源）> 远程（Bellbearer、Reed）> 近战 > Clapper，对不对？Maestro 的小机械你是清掉还是不管？
11. **Bellbearer 的铃**：你会把铃打回去砸怪、或者踩铃吗（像 Bell Beast 那样）？
12. **诱导长招**：有没有你知道的"站在某个距离 / 高度，某个怪一定出某招"？例如 Clapper 在你上墙后只跳 / 施法（录像已证实），其他怪有类似的吗？
13. （可选）方便时录一场你的 Forum 手打：站位参照和每秒按键数对比。

## 9. 需要你决定的事项

1. **算力口径**：M2 Forum 期用"实战每场 tick p99 中位数 ≤ 15 ms、迟到跳帧中位数 ≤ 10"（与 Bell Beast 过门槛时同一水平），3–4 ms 留到 M3 之后（§4.5 的路线）。还是先把 Bell Beast 降到 4 ms 再做 Forum？
2. **Q3 与多段攻击**：现规则 h = 2 时支撑里有多段事件就退出。若 R0 实测各类整链伤害有上限（例如鞭整链最多 2），是否改为"按实测整链伤害计入 D1，不单独因多段退出"？（安全规则，按 DESIGN §3.5.8 由你定；你答第 8 节第 1 题后再定也可以。）
3. **训练 mod 命令**："从第 i 波开始"或"前面波次一击死"，只在训练副本用（R1 的探针结果出来后再请你确认具体做法）。
4. **字典序**：默认不改（"不被困"进 J）；若 R5 的 A/B 显示做成新一级（V 之后、P 之前）明显更好，再请你同意改 DESIGN §3.5.4。

---

## 附录 A：本文测量的复现

全部离线、`SetPriorityClass(BELOW_NORMAL)`（`lowrun.py` 包装）、main 的 venv、`PYTHONPATH` 指向本工作区的 `brain`；脚本在会话临时目录，未提交（R0 把需要的做成正式工具）。

- 表 A、C、D：`bench_tick.py <录像 20261003_144536_BellBeast_eval_planner_oracle/rec/2026-10-03/TRAIN/i4_000> 4000`：按 `planner_bench` 的流程开环回放（录像的按键作前缀），前 50 tick 不计；每 tick 另外计时：Bell Beast 预测上的两种栅格（`Forecast.occupied`）、`forecast(4.0)`，以及规划器自己的 441 行候选经 `hold_filter_jit` 后的 `kin.rollout`（nominal 全部、bounds_lo 前 96、bounds 全部、bounds_lo 全部）。
- 表 B：`python -m ssbot.tools.kin_bench_forum --n {400,192,128,96,512} --T {36,48} --reps 120 --threads 4 --lanes nominal,bounds,bounds_lo`。
- 表 E：`forum_tpl_bench.py`：读 `C:/modeling/silksong_bot/.claude/worktrees/wf_946a7803-63c-2/knowledge/1.0.30000/enemies/forum/*_hitboxes.npz`（13 场的表，只读），按 `_load_planner_templates` 的做法取每状态支撑模板、膨胀 (0.15, 0.25) u、打包 `SupportQuery`；查询用随机放置（锚点 x 16–47）和一团 Forum 规模的候选点（N × 37 步）。
- 数据量：各 Forum 数据运行的 attempts 文件里 CLEAR 的场数。
