# M2：视觉等效视图下的 Bell Beast（任务 V，2026-10-02 晚）

目标（M2 门槛的条件）：degraded_dust 视图（ObservabilityFilter VISION_EQUIVALENT + 简单噪声 + DelayLine 2–4 帧 + 冒烟前兆）实战 CLEAR ≥ 90 %、0 WOULD_DIE、有效 ≥ 150 场，且只用视觉系统能拿到的信息。工作区 `.claude/worktrees/wf_946a7803-63c-1`，分支 `worktree-wf_946a7803-63c-1`。

## 起点

- 6ab67e1 的 degraded_dust（`20261002_173956`）：有效 36 场，CLEAR 8（22 %），QUIT 28（Q6 21 场）；28 次受击里 19 次是落铃 M2（二阶段），下劈每次冲撞 0.024 次（oracle 视图 0.97），击杀用时中位数 170 s（oracle 58 s）。每次受击几乎都退出（h 2 时 Q5 / Q6），所以 CLEAR 率基本就是"整场 0 受击"的比例。
- 受击前的决策日志（`hits_173956`，每 10 个 tick 抽一行）：M2 受击前 45–60 帧一直 FORCED_RISK，hero 在场地中部，支撑是 M2 的 self 模板（全部记录过的下落与两侧弹跳的并集，按冒烟前兆的时间 ±0.1 s 摆放）。

## 诊断：同一场战斗在两种视图下重放（`tools/view_compare`）

oracle 录像 `20261002_171806` i0 ep2（3269 tick）按录像里的实际按键作前缀，分别用 oracle 和 degraded_dust 的 PlannerPolicy 重放（监督器的暂停被丢弃，两种视图都一直规划）。按录像的 Control 状态分组：

| 状态 | oracle FORCED / 下劈生成 / 接受 | degraded_dust（6ab67e1 代码） |
|---|---|---|
| Charge | 6.1 % / 104 / 3.0 | 30.7 % / 3.9 / 0.0 |
| Dig In | 0 % / 55 / 2.4 | 0.7 % / 0.2 / 0.1 |
| Charge End | 0 % / 37 / 4.8 | 0 % / 0 / 0 |
| Rage Pos / Rage Antic | 0 % / 0 % | 57 % / 100 % |
| Ptn R（落铃下落中） | 0 % | 57 % |
| Burst Antic / Emerge Antic C（落铃下落中） | 0 % / 0 % | 100 % / 100 % |

查到的原因（都在视图一侧，不是规划器本身）：

1. **受击箱表的参考点错了。** `knowledge/1.0.30000/enemies/BellBeast_hurtbox.json`（视图按阶段放的可打框）按根 transform 建表，运行时却放在 Entity.pos（§4.1：根碰撞体中心）上。Bone Beast 的根碰撞体中心比 transform 低 2.35 u、沿朝向偏约 3 u：f 187634（Charge）预测框 y −0.50..2.55，实际 1.84..4.90——整段冲撞框都在地面以下，所以视图下从不生成下劈。
2. **落铃的精确路径只在 oracle 视图。** `Forecaster._det_bell` 读 FSM 状态和日志速度，视图下没有，只剩 self 模板并集。
3. **狂暴在地下看不见。** Rage Pos / Rage Antic 时 Boss 不绘制，视图从 Submerged 往下走所有分支（冲撞、跳砸、铃爆、狂暴），整个地面在 0.5–0.7 s 内都被覆盖。
4. **攻击开始时间。** 视图从冒烟前兆估计（±0.1 s），再用 AttackFit 在 Boss 站在锚点不动的帧上拟合（这些帧没有时间信息），冲撞框 +6 帧最多偏 2 u；AttackFit 还把跳砸的顶部在 p99 推偏 4.4 u。
5. **numba 新特化。** `kinematics.rollout` 的 events 用 `np.broadcast_to` 得到只读视图，形状已是 [n, T] 时 `ascontiguousarray` 原样返回，只读数组是另一个特化：`simulate_bound_par` 在新工作区的战斗中途编译（此前误以为是"真实地形"特化）。视图下的 `clip_fractions` 也没预热。

## 做法（全部是视觉可得的信息）

- **落铃路径来自轨迹**（`combat/bell_track.py`）：落铃从开始下落那一帧才绘制（`20261002_171806` i0_000：178 / 178 次首帧在 Air、y 13.74、速度 (0, −17)，写入注册表 `start`），竖直下落（FSM 置 vx 0），落地一次以 ±4 u/s、vy 30 弹向随机一侧，第二次触地沉入地面。所以路径由三个数决定：下落列 x（下落段检测的均值）、下落时刻（每个下落检测的高度在已知下落曲线上反解，取中位数，减半个物理步）、弹跳方向（首次触地后 x 漂移的斜率超过 5σ 且 ≥ 2 u/s 才定，之前两侧都算）。路径用注册表物理（50 Hz 步，从下落开始）按"距下落的时间"采样，时间余量照用 DET_SLACK_S，接触皮再加 3σ 的列 x 不确定度（σ 取视图位置噪声）。最近两次检测偏离模型 > 0.6 u（或 5σ），或 hero 在铃的攻击可达范围内出刀（可能拼刀改向，视图没有拼刀事件），就撤回，回到 self 模板。只用检测（visible_frac > 0），不用视图的速度。
- **受击箱表**：按 Entity.pos 重建；`recover` 按家族再分一份（`recover/BB_CHARGE` 是 Charge End 的框，`recover/BB_LEAP` 是 Leap Land 的框），视图由前一个阶段知道家族（`BossTracker.shape_key`）。
- **攻击开始时间**：每进入一个绘制阶段（入口可见 ±1 帧），按家族记录的该状态入口偏移中点重定。AttackFit 默认关闭（`planner_policy.FUSION`）。
- **Boss 位置融合**：框的位置取本次攻击最近 10 个（x）/ 30 个（y）检测，各自沿家族平均路径推到原点再平均（`BossTracker.fused_pos`）。
- **下劈闸门的确定框**（`Forecast.certain_boss`）：视图下下劈只有在每条时序分叉都碰到"确定区域"才算接上：预测形状按实测残差腐蚀（各平移的交集），残差来自 `tools/boss_path_audit --view degraded_dust --margins`（同一视图、同样噪声与延迟，只取 Boss 还在原阶段的帧，各边最大值 + 0.1 u），按视野分桶（≤ 6 / 12 / 24 / 48 帧），且只在该阶段最早可能结束之前有效（形状在阶段切换时会变）。冲撞：左 0.68、右 0.45、下 0.14、上 0.17 u（`BellBeast_vision_box_margin.json`，`20261002_171806` 14 场）。oracle 视图不变。
- **狂暴是 FSM 规则不是抽签**：一阶段、未狂暴、决策时 Boss HP ≤ 75 就只有 Rage Pos 一个后继。记录：一阶段 HP ≤ 75 的决策 311 / 311 进 Rage Pos，> 75 的 1990 次 0 次（`20261002_123347`、`125420`、`131638`、`171806`、`173956`，HP = 150 − 日志命中伤害）。视图的 HP 只数看到的命中，漏数只会让估计偏高，所以估计 ≤ 75 时确定。
- **其他**：`Forecast.committed()` 带上精确路径的铃（原来丢了，两种视图的地下风险图都看不到下落中的落铃）；rollout 的 events / dt / fs 一律可写；预热用 TERRAIN 消息构造的场地并预热 `clip_fractions`（重放 3000 帧后两种视图都没有新特化）。

## 安全核对（离线）

- **留出召回**（`support_recall` i2_002 / i3_002，35 场，留出表 `C:/ssbot/data/m2_heldout/tables`，滞后 2/3/4，margin 0）：新代码（a479c09，落铃轨迹 + 狂暴规则）下 oracle 23,896 / 23,896、ve_dust + SimpleNoise（`--noise-seed 7`，含漏检惯性延续）23,896 / 23,896，三个滞后都是 100 %。其中落铃接触帧 1,652（M2 951），攻击铃 7,339，Boss 本体 14,905。
- **落铃轨迹审计**（`tools/bell_track_audit`，`20261002_171806` i0 / i1 各 3 场，噪声种子 1）：当前时刻中心误差 p50 0.10、p99 0.33、最大 0.39 u；方向判定 0 / 18,940 错误，首次触地后 0.15–0.26 s 判定；更远时刻的大误差全部来自之后 hero 自己的横砍改向（被打铃 vx 5–12），出刀后估计即撤回。
- **框残差**（`boss_path_audit --view degraded_dust`，同上 14 场，阶段内）：冲撞 +6 帧 p10/p90 约 ±0.2 u；顶部最大 0.07 u（融合前 0.30）。

## 实战

- 7c18e6c，degraded_dust，实例 0 / 1，每实例 4 线程，种子 90000（`20261002_205247`）：20:54 起 STOP_AGENTS（主代理：5 小时额度 86 %），各打完 1 场即停。i1 ep0 CLEAR（120 s，0 受击，k 4）；i0 ep0 QUIT（81 s，被落铃 M2 打中 1 次后 h 2 时 Q6，k 3）。tick p99 12.4 / 12.8 ms（6ab67e1 的 degraded_dust 中位数 12.0），plan p99 10.4 / 10.8 ms。CPU：游戏 4 实例都在跑，只有本任务 2 个 worker，负载约 40 %。样本太少，不作结论。
- 待做：这场 M2 受击的回放（`tools/postmortem` / `view_compare`，看当时铃是在精确路径上还是退回了 self 模板，以及 FORCED_RISK 的来源）；≥ 150 场的 degraded_dust 主跑；oracle 视图回归（CLEAR 不得下降：本次改了 oracle 也用的狂暴规则、committed() 带落铃、rollout 可写事件）。
