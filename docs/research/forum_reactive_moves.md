# Forum 敌人在冲刺斩前的"闪身"：是招还是走动，由大黄蜂的什么决定（PC 1.0.30000）

**问题（你，2026-10-04）：** "有时候冲刺斩快打中的时候怪会往后或者往前闪一下，这个动作是一招吗？还是就是普通移动？这个闪身绝对是由大黄蜂动作决定的。"

**标签：** 【包】离线 UnityPy 读训练副本场景包 `hang_04_boss.bundle`、`globalgamemanagers`（层矩阵）、主角预制体包（只读）；【码】反编译 1.0.30000 C#（`C:\ssbot\decomp\1.0.30000`）；【录】录像统计（下面"数据"）；【推】由代码或数据推出、未单独实测。没有连接任何游戏实例。

**数据：** R0 = 随机数据策略的 142 场完整连战（`C:\ssbot\data\m2_forum_r0\cache` 107 场 + `cache_fresh` 35 场）；R1 = 定点采集 data2 / idle 策略的 218 局波次起点（`20261004_105441` … `153511`、`144623`，本次用 `forum_extract` 抽到 `C:\ssbot\sandbox\reactive_scripts\cache_r1`）；人 = 你的 4 段录像（`20261004_002749`、`012300`、`091214`、`133855`，58 次尝试，`forum_demo` 扫描）。

**脚本与原始输出：** `C:\ssbot\sandbox\reactive_scripts\`：`dump_enemies.py` → `out\*.txt`（每类一只的全部子物体、层、碰撞体、触发器组件和全部 PlayMaker FSM 逐动作解码）、`ranges.py` → `out\ranges.json`（每个实例每个 AlertRange 的世界形状；注意它每个 GameObject 只留最后一个碰撞体，Reed Evade Range 的两个盒子以 `reactive.py` 的 `RANGES` 为准）、`layers.py`（层矩阵）、`hero_layers.py`（主角哪些碰撞体能被 Hero Detector 看见）、`st.py` / `line_state.py`（查状态）、`reactive.py`（v4）→ `reactive_full4.json`（+ `.events.json`，录像统计，**本文的数字**）、`outliers.py` / `bell_swap.py`（触发器外的 Bellbearer 事件逐个查）、`probe_dash_stab.py`（**写好、没跑**的实机探针，§3.4）、`factcheck\`（核查时的 `instant3.py`、`indep.py`、`reed_def.py` 及输出）。复现见 §5。

**修订（同日，核查后）：** 第一版（`reactive_v3.py` → `reactive_full3.json`）的逐帧扫描只看"上一帧导出了源状态"的转移，漏掉了源状态只停留 0 帧的转移（例如 Reed `Stab Recover → Alert → Evade Antic` 在同一帧完成）：R0 漏了 Reed 闪避 1078 / 2273、举盾 1534 / 2494，所以"100 % 在盒内"的分母不全，Reed 举盾的比例（0.27）也被拉低了。v4 改为从控制 FSM 的事件流取"每一次进入源状态"（含 0 帧），本文全部数字已按 v4 重算。另外改正：Clapper 被打中的效果换成正确的对照（§0 第 4 点）；"往前闪"的来历（§2.4）；Reed 举盾是慢慢贴近而不是前冲；冲刺斩命中只算主角自己的冲刺斩伤害体；行为表协变量检验改为逐级回退平滑；Bellbearer 盒外事件的计数；DASH_IN 没出冲刺斩的原因。

---

## 0. 摘要（可直接转述）

1. **是招，不是普通走动。** 速度上像"闪一下"的都是专门的 FSM 状态，先一个很短的起手，再按自己的朝向用固定速度往后蹿：Reed `Evade Antic → Evade` 0.133 s 后 30 u/s，退约 4.9 u；Choir Bellbearer 0.083 s 后 32 u/s，约 5 u；Minister 0.1 s 后 25 u/s，约 6.4 u；Choir Clapper `Evade Scuttle` 15 u/s 退约 5.4 u；Clawmaiden `Tele Out Antic` 0.183 s 后瞬移【包】【录】。另外两种动作慢得多：**Choristor 的跳步**（`Hop Back` / `Hop Forward`，12 u/s、一跳约 2 u，连跳 1–3 下）是它两招之间的走位；**Reed 的举盾**（`Defend Start → Defend`）用 DistanceFly（最高 4 u/s）飘到离你 3 u，0.6 s 里朝你挪约 1.1 u（中位数），是慢慢贴近，不是前冲【包】【录】。
2. **你说得对：是大黄蜂决定的——但决定它的是你的身体到了哪里，不是你按了什么。** 这些"进盒就闪"的感知都是挂在敌人身上的触发盒（`AlertRange`，第 13 层 Hero Detector）；第 13 层只和 3 / 6 / 9 层碰撞，这三层上带碰撞体的只有主角本体那个 0.5 × 2.08 的物理盒。主角的刀（第 17 层）、受伤盒（第 20 层）碰不到这些触发盒；Forum 敌人身上也没有 Attack Detector（第 31 层）；Choristor 跳的方向读的是它和你 transform 的 x 距离，同样只是位置。没有任何控制 FSM 的动作读你是否在出刀、冲刺或按键【包】【码】。所以冲刺 / 冲刺斩引发闪身，是因为冲刺（28 u/s）和收割者冲刺斩的前冲（50 u/s 起、每步 ×0.85，约 6.7 u）在零点几秒里把你的身体送进了它的触发盒，它在进盒的那一帧或下一帧就开始闪【包】【码】【录】。
3. **录像核对：位置一项就够，动作不加信息。** 把控制 FSM 的每一次转移都算上，闪身发生时你的身体在触发盒里的比例（R0）：Clapper 5310 / 5310、Reed 闪避 2252 / 2273（99.1 %）、Reed 举盾 2463 / 2494（98.8 %）、Bellbearer 4468 / 4517（98.9 %）；R1、你的录像同样 98–100 %。盒外的少数大多发生在波次刚刷出、它第一次进入 `Alert` / `In Range` 时，原因未查清【录】。按"这一次进入源状态里，你的身体第一次在盒内（门槛已开）时你在干什么"分组，之后闪不闪的比例（R0，无动作 / 出刀 / 冲刺）：Bellbearer 0.97 / 0.97 / 0.99；Clapper 0.49 / 0.49 / 0.43（它每次进 `Idle` 抛一枚 50 % 硬币；冲刺组区间 [0.34, 0.51]，三份数据合计 84 / 184 = 0.46）；Reed 闪避 0.87 / 0.85 / 0.92；Reed 举盾 0.45 / 0.44 / 0.50（硬币 0.5）；Minister 在盒内 0.485、盒外 0（1282 / 2642、0 / 2883）；Choristor 往后跳的概率按"距离 ≤ U(6, 10) 就往后"的公式算和实际**逐组相等**（你的冲刺斩之后：实际 0.523、公式 0.530）。唯一明显低的一格是**刀先到**：你的冲刺斩之后 Reed 只闪了 9 / 16、出刀时 79 / 107（被打中的 Reed 转去 `Stab Pos` 刺你）。决策表加"主角当前动作"作协变量，留出对数损失几乎不变（R0 +0.003、R1 −0.001、你的录像 +0.003 nats / 决策）【录】。
4. **真正"由动作决定"的是打中之后的反应**（要先打中，来源可以是任何人，Garmond 也算）：Clapper 在 `Idle` 被打中 → `Dmg Attack` → 你在它锤的范围里就进 `Close Range`（SLAM / EVADE / CAST 各 1/3）→ 实际闪 23 %（R0 403 / 1739）。和"不打它"比要分两种：它进 `Idle` 不到 0.25 s、硬币还没亮出来时被打中，闪的机会从约 0.49 **降到** 0.25（R0 254 / 1010；R1 0.23、你 0.15）；门槛已开、你在盒里它却没闪（硬币是反面，这一轮本来不会闪）之后被打中，闪的机会从 0 **升到** 0.20（R0 149 / 729；R1 0.20、你 0.31）。Reed 在 `Alert` 被打中 → `Stab Pos`（转头刺你），在 `Stab Pos` 再被打中 → 立刻 `Stab Antic`；Minister 被打中 → 下一招提前（攻击计时截到 ≤ 0.5 s）；Maestro 被打中 → 立刻进入下一次出招选择；Envoy 走路时被打中 → 冲锋【包】【录】。
5. **你最可能看到的是谁【推】：** 你的 329 次冲刺斩（Reaper 257、Wanderer 72）里，前方 8 u 内最近的敌人：Choristor 137 次（−0.1…+0.6 s 内跳了一步 62 次，58 次往后）、Reed 86 次（举盾 17、闪避 6）、Clapper 36 次（后撤 9）。但 Choristor 本来就一直在跳：冲刺斩前后这个窗口里它开始跳的比例是 45 %（76 / 168），平时同样距离的窗口是 33.5 %（4575 / 13670），只多一点；它一跳 12 u/s、约 2 u，不算"闪"。速度够得上"闪一下"的只有 Reed / Bellbearer 的闪避（30 / 32 u/s）和 Clapper 的后撤（15 u/s）。所以**"往后闪"最可能是 Reed 的闪避**（也可能是 Clapper 后撤或 Choristor 后跳）；**"往前闪"**的候选：Choristor 前跳（离它远于 6–10 u 时）；Reed 闪避里约 10 % 最后落在你这一侧——你在它正上 / 正下方 1 u 内，或在它 0.133 s 起手期间冲到了它另一边（它按起跳那一刻背离你退，相对起跳时你的位置只有 9 / 2273 次是朝你退的）；最弱的一种是 Reed 举盾的慢速贴近。实机探针（§3.4）能定。时间上：冲刺斩的刀在动画开始后 0.117–0.133 s 打中（p5–p50，只算你自己的冲刺斩伤害体，226 次）；Reed 从你进盒到真正移动要 0–1 帧 + 0.133 s，所以冲刺斩开始时才进盒往往是刀先到（Reed 闪避 6 次：先打中 3、没打中 2、先闪 1），冲刺途中就进了盒的会被闪掉。Reed 有反应动作时你的冲刺斩只打中 10 / 23（43 %），没有时 48 / 63（76 %）【录】。
6. **对 bot：** (a) **安全不受影响**：这些闪身都已在支撑里（行为表从 `Alert` / `In Range` / `Idle` / `Evade?` / `Hop Check` 都记录了这些后继，停留下限正好等于 FSM 的门槛：Bellbearer 0.508 s、Clapper 0.250 s、Reed 0），本身没有攻击碰撞体，只有身体伤害；落点在你那一侧的那几种（上一点）模板也按它自己的朝向记录，同样在支撑里。(b) **预测 / 规划要改的是打分**：闪不闪是"候选计划的身体轨迹第一次进它的触发盒"的函数（加几枚看得见或可推断的门槛和硬币），建议在 MultiForecast 的打分里加一个"反应分支"（只进 J / P，不进 S）：候选在 t 进盒 → 以 p 在 t（至多 + 1 帧）进入闪身。p（R0，按每次进入源状态）：Reed 闪避已上膛时你在它 `Alert` 期间进盒 ≈ 0.95、它进 `Alert` 时你已在盒里 ≈ 0.8；Reed 举盾 ≈ 0.45（硬币 0.5，同一帧 EVADE 先查）；Bellbearer ≈ 0.97；Clapper ≈ 0.49（硬币）；Minister 0.485。它也给出两种打法：**趁它"子弹打空"时冲**（Reed 闪过一次后，要等下一次举盾或突刺才会再闪；Bellbearer 闪过一次后，要等下一次扔铃）、**别在 7.65 u 内对着可能举盾的 Reed 冲**（会撞盾吃 2 格反击）。归属：R5（和"决策的感知时刻"是同一份 FSM 静态提取），诱闪 / 打空窗在 R6，冲刺斩原语在 R7，打中后的反应扩进 R3 的命中效果分支。(c) **行为表不加"主角动作"**；要加就加"主角身体在某个触发盒里"这个精确几何量（Minister `Evade?` 在盒内 0.485 / 盒外 0，比距离分档干净得多），以及"刚被打中"（打中分支已能算）。
7. **顺带发现：** R1 定点采集的 DASH_IN 战术 218 局里**一次冲刺斩都没打出来**（`Dash Upper` 片段 0 次；R0 随机策略 142 场 19 次；你的录像 329 次）。它只按冲刺 2 帧，再过 U(0.04, 0.14) s 按攻击：(i) 0.1 s 之前的按键落在冲刺本身里，冲刺中 `CanAttackAction` 不许出刀【码 `HeroController.cs` 11002–11009】；(ii) 约 40 % 的按键在 0.1 s 之后，可是冲刺键早就松了，冲刺结束时 sprint FSM 直接交还控制（冲刺斩只在 sprint FSM 的 Reaper Antic / Upper 里），出的是普通横斩【码 `forum_policy.py` 376–398；`movement_kinematics.md` §1.3】【推】。改法：按住冲刺键穿过整个冲刺和之后的 sprint（≥ 0.25 s），在 0.1 s 之后、仍按着时按攻击；采 R7 数据前先按"每局 `Dash Upper` 片段数"验一遍。

---

## 1. 静态：每类敌人的"闪身"状态和进入条件

### 1.1 敌人能"感知"大黄蜂的哪些东西【包】【码】

- 9 类 Forum 敌人的控制 FSM 里，读主角的方式只有：`CheckAlertRangeByName` / `CheckAlertRange`（触发盒里有没有主角）、`GetDistance` / `GetXDistance`（transform 距离；Choristor `Hop Check` 的跳向就是这个）、`FaceObjectV2` / `CheckPassedTarget` / `CheckTargetDirection`（相对位置）、HealthManager 发来的 `TOOK DAMAGE` / `BLOCKED HIT` / `HIT`（**打中之后**才有，`HealthManager.cs` 793–1091 行）、`CheckHeroPerformanceRegion`（主角在弹琴 Needolin，进 `Sing`），以及 Clawmaiden `Spin Antic` 读 PlayerData `silk`（主角丝量）。多段攻击的 `hornet_multi_wounder` 子 FSM 读 `cState.parrying` 和 `CanHeroTakeDamage`，只管连段本身。**没有任何动作读主角是否在出刀、冲刺、飞针、跳或按键**；全局转移里也没有这类事件（各类的全局转移只有 `ZERO HP`、`CALL`、`MULTI HIT CONNECT`、`GO UP/LEFT/...`）。
- 所有范围都是 `AlertRange : TrackTriggerObjects`，挂在第 13 层 `Hero Detector`、`ignoreLayers` 0、无标签过滤。层矩阵（`globalgamemanagers` Physics2DSettings）：13 层只和 3、6、9 层相碰；主角预制体、全部纹章包和 Forum 场景里，3 / 6 / 9 层上带碰撞体的只有 `Hero_Hornet` 根的 BoxCollider2D（0.5 × 2.079，非触发器，即 STATE `hero.box`）。主角攻击在 17 层、受伤盒在 20 层，都碰不到 13 层。Forum 敌人身上没有 31 层（Attack Detector，会和 17 层相碰）的子物体【包 `layers.py`、`hero_layers.py`、`dump_enemies.py`】。`TrackTriggerObjects` 只在 `cState.isTriggerEventsPaused` 时忽略主角，这个字段没有 FSM 会设【码】。
- 触发盒按物理步更新（`OnTriggerEnter2D`），FSM 在 `Update` 里每帧查（`everyFrame=1` 的地方）：所以从身体进盒到状态切换是 0–1 个物理步 + 至多 1 帧【码 `TrackTriggerObjects.cs` 168–236、`CheckAlertRangeByName.cs`】。`lineOfSight = Parent` 的盒子另要求敌人到主角之间没有地形（Forum 场地内几乎总成立）【码 `AlertRange.cs`】。

### 1.2 每类的状态、触发、门槛

形状是相对敌人 transform 的世界尺寸（含根缩放；`ranges.py` / `reactive.py` 的 `RANGES`）。"能改变它的"一栏：**位** = 只通过主角身体的位置；**中** = 要先打中（任何来源）；**无** = 与主角无关。

| 类型 | 会"闪"的状态（家族） | 怎么进去（源状态 → 条件） | 门槛 / 冷却 / 随机 | 运动 | 能改变它的 |
|---|---|---|---|---|---|
| **Choir Clapper** | `Evade Scuttle`（CC_EVADE） | ① `Idle`：每帧 `Will Evade ∧ 主角在 Slam Range ∧ Can Evade` → EVADE。Slam Range = 盒 x ±8.049、y −0.543 ± 3.913（站地时世界 y ≤ 10.82） | `Will Evade` 每次进 `Idle` 抛一次（RandomBool 50 %）；`Can Evade` 进 `Idle` 0.25 s 后才真 | 先 `FaceObjectV2`（两次转身至少隔 0.5 s），`SetVelocityByScale +15`（背离朝向）0.35 s；背后 6 u 内有墙 → `Escape Jump` → 跳砸 / 跳施法 | 位 |
| | | ② `Close Range`（从 `Walk` 的 CLOSE、`After Scuttle`、`Dmg Attack` 来）：SendRandomEventV4 SLAM / EVADE / CAST 各 1/3（eventMax 1、missedMax 3） | 刚闪过（`Evaded`，到下一次出招才清）只在 SLAM / CAST 里选；正在后退走（片段 `Walk B`）→ 直接 SLAM；另一只在出招 → 回 `Idle` | 同上 | 位；经 `Dmg Attack` 来时是中 |
| | | ③ `Idle` 另一只 Clapper 在 4 u 内 → `Avoid Type`：主角和它在同一侧 → EVADE，否则 → `Walk` | — | 同上 | 位（相对另一只） |
| | | ④ `Idle` 被打中（`TOOK DAMAGE`）→ `Dmg Attack` → 主角在 Slam Range → `Close Range`（再按 ②），否则 `Far Range` | — | — | **中** |
| **Clawmaiden** | `Tele Out Antic`（CM_TELE）：瞬移 | ① 瞬移刚落地的 `Tele In End`：每帧主角在 `Tele Escape Range`（圆 r 2.66）→ ESCAPE，马上再瞬移；② `Fly`：距离 > 20 → TELEPORT；③ `Fly` 等 1–2 s 后 `Tele?`：距离 > 22 → TELEPORT，否则 V4 50 / 50 | — | `Tele Out Antic` 0.183 s 后消失，在 `Teleplane` 里随机落点（离主角在一个区间内、离自己 ≥ 4 u） | 位 |
| **Minister** | `Evade Antic → Evade`（MI_EVADE） | ① `Evade?`（出现在 `Attack End`、`Parry Stance End`、`Parry Slash End` 之后，瞬时）：SendRandomEventV4 50 / 50（eventMax 2、missedMax 2：同一结果最多连出 2 次，不是独立硬币）直接 `Retreat?`；另一半主角在 `Evade Range`（圆 r 4.955，圆心在 transform 下方 1 u）→ EVADE；② 它自己的连斩连上之后（`Multihit → Reset Z Pos`）→ 必定 `Evade Antic` | 只在自己出招之后；不会在 `Chase` 里闪 | `Evade Antic` 0.1 s → `Evade`：`SetVelocityByScale +25`、y +5，DecelerateXY 0.95 / 0.975 | 位（①）；② 是它打中你 |
| | `Parry Stance`（MI_PARRY，举刀格挡） | `Chase` 攻击计时到且主角在 `Attack Range`（圆 r 7）→ `Attack Choice` V4 CHARGE / PARRY 1:1 | — | 在姿态里飞到离主角 6 u；**被打中**（`BLOCKED HIT`）→ 4 段反击 | 位；反击是中 |
| | （被打中） | `Chase` / `Retreat?` 被打中 → `Range Check`：攻击计时截到 ≤ 0.5 s | — | — | 中 |
| **Maestro** | 无闪避；`Defend Start`（MA_DEFEND）是召小机械围成防阵 | `Attack Choice` V4 FIRE / DEFEND 0.75 / 0.25 | — | 原地 | 无；`Fly` / `Forum Fly` 被打中 → 立刻 `Summon?`（中） |
| **Tiny** | 无；`Defend Ready` 由 Maestro 的事件指挥 | Maestro 发 `DEFEND READY` | — | — | 无（控制 FSM 没有被打中出边） |
| **Reed** | `Evade Antic → Evade`（RE_EVADE） | `Alert`：每帧主角在 `Evade Range` → EVADE。**Evade Range 是两个盒子的并集**：x ±1.479、y +0.043 ± 5.202（它正下方 / 正上方的竖条）和 x ±3.810、y +2.570 ± 2.674（与它同高到上方 5 u 的横条） | **一发子弹**：进 `Evade Antic` 时把 Evade Range 关掉，到下一次 `Defend Start` 或 `Stab Antic` 才重新打开 | `Evade Antic` 0.133 s → `Evade`：起手和起跳各做一次 `FaceObjectV2`（两次转身至少隔 0.5 s），起跳时 `SetVelocityByScale +30`、y +5；`Evade End` 50 % 回 `Alert`，否则在投掷范围内就扔针（`Evade End` 的 STAB 检查用的是已关掉的 Evade Range，永远不发） | 位 |
| | `Defend Start → Defend`（RE_DEFEND，举盾） | `Alert`：每帧 `Will Defend ∧ 主角在 Defend Range（圆 r 7.65）∧ ¬Just Did Defend` → DEFEND；Alert 里 EVADE 的检查排在 DEFEND 前面 | `Will Defend` 每次进 `Alert` 抛一次（50 %）；`Just Did Defend` 举过盾后为真，到下一次 `Stab Antic` / `Throw Antic` 才清 | `Defend Start` 0.083 s、`Defend` 1 s：`DistanceFly` 到离主角 3 u、`speedMax` 4、加速度 0.25（慢慢贴近：0.6 s 内朝你挪 p50 1.1 u，60–72 % 的情形净位移朝你一侧）；`Defend` 里被打中（`BLOCKED HIT`）→ `Block → Parry Y Aim → Parry Slash`（多段，整链 2 格，可拼刀） | 位；反击是中 |
| | （被打中） | `Alert` 被打中 → `Stab Pos`（飞到 5 u、主角进 Stab Range 就刺）；`Stab Pos` 再被打中 → 立刻 `Stab Antic` | — | — | 中 |
| **Envoy** | 无 | — | — | — | `Walker` 被打中 → `Leader?` → `Charge Antic`；`Charge` 被打中 → `Reset`（继续冲） |
| **Choristor** | `Hop Back` / `Hop Forward`（在 CH_IDLE 里，走位） | `Battle Idle` 0.2–0.3 s → `Move Start`（连跳 1–3 下、Hop Distance ~ U(6, 10)）→ `Hop Antic`（**进入那一帧**主角在 `Close Range`（盒 x ±2.885、y −0.27 ± 1.906）→ 直接去出招）→ `Hop Check`：`GetXDistance` 的 \|x 距离\| ≤ Hop Distance → `Hop Back`，否则 `Hop Forward`；`Slash Check` 脚下前方没地 → `Cancel To Hop Back` | Hop Distance 每次 `Move Start` 抽一次 | `SetVelocityByScale ±12`，一跳 0.15 s 约 2 u；落地数跳数，跳完去 `Attack Choice` | 位 |
| **Choir Bellbearer** | `Evade Antic → Evade`（CB_EVADE） | `In Range`：每帧 `主角在 Evade Range（盒 x ±3.297、y ±6.659）∧ 背后 3 u 内没有墙（射线）∧ Can Evade ∧ ¬Evade Cooldown` → EVADE；`Out of Range` 主角回到投掷范围时的 `Insta Throw?` 同样检查一次 | `Can Evade` 进 `In Range` 0.5 s 后才真；`Evade Cooldown` 在 `Evade` 置真、下一次 `Throw Antic` 才清（**一发子弹**，扔一次铃补一发） | `Evade Antic` 0.083 s → `Evade`：`SetVelocityByScale +32`、y −8 | 位 |

几个细节【包】：`SetVelocityByScale` 的正数是"背离朝向"（这些精灵默认朝左：Clapper 的锤冲 −30 是往前，forum.md §10.1）。Reed 的速度在**起跳**（`Evade`）时按那一刻的朝向设，而 `Evade` 进入时又做了一次 `FaceObjectV2`：所以它是背离"起跳那一刻的你"退的（§2.4）。Bellbearer 的模板 FSM `FSM`（`FLYER RESPONSE`、`GO UP/DOWN/LEFT/RIGHT`）只是飞行物互相推开，和主角无关。

### 1.3 和行为表的关系

`gauntlet_tables.FORUM_SPECS` 已把 `Evade Scuttle`、三个 `Evade Antic`、`Tele Out Antic`、`Defend Start`、`Parry Stance Antic` 当作家族的开始状态，`Hop Back` / `Hop Forward` 在 Choristor 的决策状态里（CH_IDLE）。表里的停留下限正好是 FSM 的门槛【录 `knowledge/.../forum/*.json` 的 `dwell_s.<源状态>.by_successor`】：Bellbearer `In Range → Evade Antic` 最短 0.508 s（门槛 0.5 s）、Clapper `Idle → Evade Scuttle` 0.2498 s（0.25 s）、`Idle → Dmg Attack` 0.0167 s（被打中随时）、Reed `Alert → Evade Antic` 0 和 `Alert → Defend Start` 0（`Alert` 里随时，含进入当帧）。

---

## 2. 录像

方法（`reactive.py` v4）：每个敌人一条按帧的状态序列和它控制 FSM 的事件流，每帧的主角物理盒（STATE `hero.box`），按 §1.2 的形状算"身体在不在盒里"（盒子四周放宽 0.05 u：20 场里 1445 次事件有 73 次离精确形状 0–0.05 u，0.05–0.3 u 之间 0 次；推测是 transform 位置和物理步位置差一帧；"在盒里"取这一帧或上一帧）。**一次访问** = 事件流里"X → 源状态"（第 fa 帧）到"源状态 → Y"（第 fb 帧）；它的决策帧是 fa…fb（FSM 进入当帧就跑一遍源状态的检查），所以 fa = fb 的 0 帧访问也算。事件 = 这次访问**直接**转到闪身状态（`Idle → Avoid Type → Evade Scuttle` 和 `Idle → Dmg Attack → Close Range → Evade Scuttle` 不算 `Idle` 的进盒闪避，单独计）。主角的动作按动画片段分：冲刺斩（`Dash Upper*`、`Wanderer Dash Attack*`）、飞针（`Harpoon*`）、冲刺（`Dash*`、`Air Dash`、`Sprint*`）、出刀（片段名含 `Slash` / `DownSpike`），"当时的动作" = 该帧和之前 0.2 s 里有没有（优先级按这个顺序），否则"无"。门槛从事件流跟踪（Reed 的一发子弹和 `Just Did Defend`、Bellbearer 的冷却和 0.5 s、Clapper 的 0.25 s）；Clapper 的 `Will Evade` 和 Reed 的 `Will Defend` 看不见。

### 2.1 事件是不是都发生在身体进盒时【录】

| 机制 | R0 事件（其中 0 帧访问） | 其中身体在盒内 | R1 | 你 |
|---|---|---|---|---|
| Clapper `Idle → Evade Scuttle` | 5310（0） | 5310 | 602 / 602 | 55 / 55 |
| Reed `Alert → Evade Antic` | 2273（1078） | 2252（99.1 %） | 995 / 996 | 209 / 209 |
| Reed `Alert → Defend Start` | 2494（1534） | 2463（98.8 %） | 1152 / 1160 | 285 / 295 |
| Bellbearer `In Range → Evade Antic` | 4517（0） | 4468（98.9 %） | 418 / 425 | 141 / 143 |
| Clawmaiden `Tele In End → Tele Out Antic` | 0（你进它 2.66 u 圈的情形没出现过） | — | 0 | 0 |

- Reed 有一半左右的闪避和六成的举盾发生在它**进 `Alert` 的那一帧**（从 `Defend End`、`Stab Recover`、`Throw Recover`、`Parry Slash End`、`Evade End` 回到 `Alert`，同帧就转走）：你已经在盒里，它一回到 `Alert` 就闪 / 举盾。
- 盒外的事件按"进源状态之前的状态"分：Reed 闪避 R0 21 次里 15 次是波次刷出后第一次进 `Alert`（`Activate → Alert`），另 4 次 `Defend End`、2 次 `Stab Recover`；Reed 举盾 31 次里 16 次 `Activate`、6 次 `Evade End`、5 次 `Throw Recover`、4 次 `Startle`；你的录像举盾 10 次里 6 次 `Activate`。Bellbearer 49 次（已放宽 0.05 u）：32 次在刷出后第一次 `In Range`（`Activate`），16 次 `Rethrow?`，1 次 `Insta Throw?`。逐个查（`bell_swap.py`、`outliers.py`，R0）：45 次另一只同名 Bellbearer（`Pilgrim 03 Song`）同一帧也在 `Evade Antic`，3 次那一帧没有另一只的导出行，1 次另一只只在 `In Range`；46 次主角那一帧也不在另一只的盒里（所以不是简单的"把另一只的事件记到这一只"）；48 次另一只 Bellbearer 的身体就在这一只的 Evade Range 里（本帧或上一帧），1 次主角离盒边 ≤ 0.2 u。敌人在第 11 层，碰不到 13 层。刷出时的触发器状态、导出把同名实体串了，还是有我没找到的联动，未查清。
- `Idle` 被打中后的闪避（不算在上表）：R0 经 `Dmg Attack → Close Range` 418 次（其中 62 次同帧又接 `Escape Jump` 等），经 `Avoid Type` 42 次；R1 经 `Close Range` 19、你 24。

### 2.2 动作会不会改变"进盒后闪不闪"【录】

按"这一次访问里，身体第一次在盒内且门槛已开的那一帧"主角在干什么分组，这次访问直接闪了的比例（Wilson 95 % 区间，括号内是访问数）：

| 机制 | 数据 | 无动作 | 出刀 | 冲刺 | 冲刺斩 / 飞针 |
|---|---|---|---|---|---|
| Bellbearer 闪避 | R0 | 0.974（3372） | 0.970（786） | 0.990（391） | 冲刺斩 1 / 1 |
| | R1 | 0.983（297） | 1.0（63） | 0.978（46） | 飞针 0.94（16） |
| | 你 | 0.962（53） | 0.985（68） | 1.0（19） | 冲刺斩 3 / 3 |
| Clapper `Idle` 闪避（硬币 0.5） | R0 | 0.493 [0.483, 0.504]（8779） | 0.485 [0.463, 0.508]（1901） | 0.425 [0.345, 0.510]（134） | — |
| | R1 | 0.481（1124） | 0.557（79） | 0.586（29） | — |
| | 你 | 0.456（57） | 0.500（28） | 0.476（21） | 冲刺斩 5 / 5 |
| Reed 闪避（已上膛） | R0 | 0.867 [0.850, 0.882]（1705） | 0.846 [0.818, 0.870]（752） | 0.920 [0.865, 0.954]（150） | — |
| | R1 | 0.791（1067） | 0.885（122） | 0.972（36） | 飞针 0.67（12） |
| | 你 | 0.902（102） | 0.738（107） | 0.893（28） | 冲刺斩 0.56（16） |
| Reed 举盾（¬Just Did Defend；硬币 0.5） | R0 | 0.453 [0.437, 0.469]（3722） | 0.444 [0.419, 0.469]（1504） | 0.502 [0.437, 0.568]（221） | — |
| | R1 | 0.461（2128） | 0.468（297） | 0.436（62） | 飞针 0.75（8） |
| | 你 | 0.430（242） | 0.412（272） | 0.562（89） | 冲刺斩 0.45（40） |

Reed 闪避再按"身体是在它 `Alert` 期间进的盒，还是它进 `Alert` 时你已经在盒里"分（无动作 / 出刀 / 冲刺）：

| 数据 | 你在它 `Alert` 期间进盒 | 它进 `Alert` 时你已在盒里 |
|---|---|---|
| R0 | 0.958（762） / 0.912（260） / 0.968（94） | 0.793（943） / 0.811（492） / 0.839（56） |
| R1 | 0.910（288） / 0.973（37） / 1.0（19） | 0.747（779） / 0.847（85） / 0.941（17） |
| 你 | 0.966（59） / 0.765（51） / 0.909（22）；冲刺斩 5 / 10 | 0.814（43） / 0.714（56） / 0.833（6）；冲刺斩 4 / 6 |

- Bellbearer 几乎是确定的（门槛开时进盒就闪），三组相同。
- Clapper 的比例就是那枚 50 % 的硬币（硬币正面就在第一个机会闪，所以"闪了 / 有机会的访问"就是硬币；之后被打中的访问算反面，没有偏差）。第一版里 R0 冲刺组的 0.32 是漏算 0 帧和同帧连跳（`Idle → Evade Scuttle → Escape Jump`）造成的，重算后是 0.43、区间与其他组重叠，三份数据合计 84 / 184 = 0.46。
- Reed 闪避不是 1，低的地方有两种：(1) **刀先到**：被打中会先进 `Stab Pos`——你的出刀组 0.74、冲刺斩组 0.56 就是这个（R0 出刀组不低【推：随机策略的刀很少够得着空中的 Reed】）；(2) 它进 `Alert` 时你已在盒里的访问只有 0.75–0.84，你在它 `Alert` 期间进盒的有 0.91–0.97。(2) 的原因没查清【推：`Defend Start` / `Stab Antic` 重新打开 Evade Range 后，触发器要到下一个物理步才登记已在里面的主角；或同一帧 `Choice` 计时到期】。
- Reed 举盾就是硬币 0.5，略低是因为同一帧 EVADE 先查（你同时在已上膛的 Evade Range 里时它闪不举盾）。冲刺组在 R0 / 你的录像略高（0.50 / 0.56），R1 没有（0.44）；你从远处冲进来时先进 7.65 u 的 Defend Range、还没进 Evade Range，DEFEND 先拿到这一帧——这是进盒的先后（位置），不是动作【推】。

逐帧的分层检验（每个决策帧"这一帧闪没闪"，按 |dx| 1 u × dy 1 u × 左右分层，只看"在盒里、门槛开"的帧，Mantel–Haenszel 合并比值比，`reactive_full4.json` 的 `cmh_in_range_gate`）给冲刺组 1.3–2.0 倍（R0：Bellbearer 1.68 [1.17, 2.42]、Reed 闪避 2.02 [1.53, 2.66]、Reed 举盾 1.34 [1.10, 1.64]、Clapper 1.36 [1.04, 1.79]），出刀组 R0 0.86–1.22（Clapper 1.05 [0.97, 1.13]、Reed 闪避 1.22 [1.07, 1.38]、Reed 举盾 1.11 [1.01, 1.22]、Bellbearer 0.86 [0.68, 1.08]），R1 的 Clapper 出刀组 2.31 [1.66, 3.21]。这是计数方式造成的：闪身发生在第一个机会帧，之后"在盒里却没闪"的帧全是硬币反面的访问拖出来的；冲刺的主角很快出盒、出刀的主角很快把它打进 `Dmg Attack`，都会缩短这些"白等"的帧，比值比就变大——它量的是反面访问拖多久，不是闪的概率。按每次访问算（上表）才是"动作会不会改变闪的概率"的正确问法。

**瞬时决策**（`reactive_full4.json` 的 `decisions`）：

- **Choristor `Hop Check`**：公式 P(往后) = clamp((10 − |dx|) / 4, 0, 1)（Hop Distance ~ U(6, 10)）和实际逐组相等：R0 无动作 0.462 / 0.457（实 / 算，n 6364）、出刀 0.557 / 0.546（2193）、冲刺 0.452 / 0.461（219）；R1 0.486 / 0.486、0.636 / 0.644、0.642 / 0.628；你的录像 无 0.325 / 0.321（1146）、出刀 0.476 / 0.471（826）、冲刺 0.223 / 0.222（373）、**冲刺斩 0.523 / 0.530（216）**。分层比值比（|dx| 1 u × dy × 是否在盒里）冲刺斩 1.02 [0.55, 1.91]、冲刺 1.00 [0.50, 2.02]（你）。
- **Minister `Evade?`**：盒内闪 1282 / 2642 = 0.485、盒外 0 / 2883（R0）；R1 404 / 854 = 0.473、0 / 500；你 35 / 70 = 0.50、0 / 107。出刀 / 冲刺组的比值比 0.90 [0.76, 1.06]（R0）、0.85 [0.55, 1.30]（R1）。
- **Clapper `Close Range`** 选 EVADE：从 `Walk` 来 814 / 11596 = 7.0 %（R0）、从 `Dmg Attack`（刚被打中）来 403 / 1705 = 23.6 %、从 `After Scuttle`（刚闪过）来 0 / 1265（`Evaded` 门槛）；R1 6.0 % / 21 % / 0、你 — / 21 % / 0。扣掉"另一只在出招 → 回 `Idle`"之后，`Dmg Attack` 来的是 403 / 1149 = 35 %（≈ 1/3），`Walk` 来的是 814 / 6001 = 14 %：`Walk` 一路低是 FSM 的细节（后退走的 `Walk B` 直接 SLAM、刚闪过的不再 EVADE），**不是"没被打中"的对照**；被打中的效果见 §0 第 4 点和 §3.2 第 5 点。`Dmg Attack` 去 `Close Range` 当且仅当主角在 Slam Range（1705 / 1709；盒外 1856 / 1856 去 `Far Range`）。
- **Clapper `Idle` 被打中的效果**（`clapper_idle_hit`，结果 = 打中后那一串决策的第一个真实状态是不是 `Evade Scuttle`）：门槛开之前被打中、你在盒里 R0 254 / 1010 = 0.25（R1 10 / 44、你 12 / 80）；门槛开了、你在盒里它没闪之后被打中 149 / 729 = 0.20（R1 9 / 45、你 12 / 39）；被打中时你在盒外 16 / 1917 = 0.008（去 `Far Range`）。对照：没被打中时硬币 ≈ 0.49（上表）；硬币已亮出反面后不打它，这一轮是 0。（核查时用"0.7 s 内任何路径闪"的口径得 0.32 / 0.30，多出来的是被打中后回 `Idle`、下一轮新硬币的闪避，`factcheck\indep.py`。）
- **Clapper `Avoid Type`**（主角和另一只同侧才闪）：R1 出刀组比值比 4.9 [2.5, 9.8]——分层里没有"另一只在哪边"，是混杂，不是因果（FSM 只读两个方向）。

### 2.3 反应延迟【录】

- **从身体进盒到状态切换**（门槛已开时）：Reed 闪避 p50 0（一半是它回到 `Alert` 的那一帧你已在盒里），p95 0.05 s（R0）/ 0.042 s（你）；你在它 `Alert` 期间进盒时是下一帧（第一版只看导出帧时 p50 0.017 s）。Reed 举盾 p95 0.017 s。Clapper 和 Bellbearer 的 p50 是 0.27 s 和 0.017 s、p95 0.28 s 和 0.53 s：主角**已经**在盒里、它刚进 `Idle` / `In Range` 时要等 0.25 / 0.5 s 的门槛；门槛开着时进盒同样是同帧或下一帧。
- **从你的动作开始到它切换**：分布很宽，因为取决于动作开始时离盒子多远（`reactive_full4.json` 的 `delay_from_*_start_s`）。
- **从状态切换到真正开始移动**（起手）：Reed 0.133 s、Bellbearer 0.083 s、Minister 0.1 s、Clapper 立刻（15 u/s）、Choristor 立刻（一跳 0.15 s）、Reed 举盾 0.083 s、Clawmaiden 0.183 s 后消失。退开的距离（0.6 s 内，背离你那一侧为正）p50：Reed 4.9 u、Bellbearer 5.0、Minister 6.4、Clapper 5.4、Choristor 后跳 1.9 / 前跳 −2.0、Reed 举盾 −1.1（朝你）。
- **冲刺斩的命中时间**（你的录像，前方目标被你自己的冲刺斩伤害体 `DashUpper Slash` / `DashStab` / `DashStabAlt` 打中的 226 次）：冲刺斩动画开始后 p5 0.117 s、p50 0.133 s、p95 0.217 s。第一版的 230 次里混了 Garmond 的伤害体（WildSlash 7、Charge 2、Stomp 1）。

### 2.4 "往前闪"的来历【录】

0.6 s 内净位移落在"进状态时你所在的那一侧"（< −0.5 u）的比例和原因（`toward`）：

| 动作 | R0 比例 | 原因（R0） |
|---|---|---|
| Reed 闪避 | 221 / 2273 = 9.7 %（R1 11.9 %、你 10.0 %） | 你在它 x ±1 u 内（Evade Range 的竖条，左右没定义）130；你在 0.133 s 起手期间冲到了它另一边、它背离起跳时的你退 52（冲刺组 49 / 141 = 35 % 落在旧的一侧）；先退开、0.6 s 内又飞回来 39；转身被 0.5 s 间隔挡住 0 |
| Bellbearer 闪避 | 128 / 4524 = 2.8 % | 你在 x ±1 u 内 113、起手期间换边 8、飞回来 7 |
| Minister 闪避 | 81 / 2372 = 3.4 % | 你在 x ±1 u 内 63、飞回来 16、换边 2 |
| Choristor 后跳 | 94 / 4275 = 2.2 % | x ±1 u 内 50、跳回来 21、转身被 0.5 s 挡住 15、其他 8 |
| Clapper 后撤 | 4 / 9389 | x ±1 u 内 4 |
| Reed 举盾 | 68 %（R1 72 %、你 60 %） | 它本来就飞向离你 3 u |
| Choristor 前跳 | 86 % | 它本来就往前 |

相对**起跳那一刻**你的位置，Reed 闪避只有 9 / 2273（R0）、0 / 996（R1）、0 / 209（你）是朝你退的。所以第一版"你冲过它身后、它还没转身"的解释不成立。你看到的"往前闪"有三种来源：Choristor 的前跳（距离 > 6–10 u 时）、Reed 闪避在你从它头顶 / 脚下或起手期间穿过时落在你原来那一侧、以及 Reed 举盾的慢速贴近。

### 2.5 你的冲刺斩（329 次：`Dash Upper Antic` 254、`Wanderer Dash Attack` 72、其他 3）【录】

前方 0–8 u 最近的敌人，冲刺斩开始前 0.1 s 到后 0.6 s 内有没有反应动作、有没有被**你的冲刺斩**打中（先后按"命中时刻"和"状态切换时刻 + 起手"比）：

| 目标 | 次数 | 打中 | 反应动作 | 反应时打中 / 先后 |
|---|---|---|---|---|
| Choristor | 137 | 116 | 62（后跳 58、前跳 4） | 51 / 62；后跳：先跳 29、先打中 18、没打中 11；前跳：先跳 3、先打中 1 |
| Reed | 86 | 58 | 23（举盾 17、闪避 6） | 10 / 23（无反应 48 / 63）；举盾：没打中 11（撞盾或没够着）、先打中 4、起手中打中 2；闪避：先打中 3、没打中 2、先闪 1 |
| Clapper | 36 | 30 | 9（`Evade Scuttle`） | 7 / 9：都是它先动、刀照样追上（15 u/s 跑不过冲刺斩）；没打中 2 |
| Envoy / Clawmaiden / Bellbearer / Minister / Tiny | 12 / 10 / 6 / 3 / 3 | 9 / 7 / 3 / 3 / 0 | 0 / 0 / 1 / 2 / 0 | — |

Choristor 的跳是它一直在做的走位（每次 `Move Start` 1–3 跳）：冲刺斩前后窗口里开始跳的比例 76 / 168 = 45 %，平时同样距离（前方 0–8 u）的窗口 4575 / 13670 = 33.5 %【录 `factcheck\indep_human.json`】；冲刺斩只是把距离缩短，所以多半往后跳（方向按 §2.2 的公式）。

---

## 3. 对 bot 的含义

### 3.1 安全（S）【推，依据 §1.3 和 forum.md §12.2】

- **都在支撑里。** 闪避 / 跳步 / 瞬移 / 举盾都是行为表里已有的家族或决策后继，停留区间按录像记录（下限等于 FSM 门槛），R0 的支撑召回在 35 场新数据上已认证 100 %（forum.md §12.2），这些状态都在那批数据里。闪身本身没有攻击碰撞体，只有身体（Clapper 2 格，其余 1 格）；落点在你原来那一侧的那几种（§2.4）模板按敌人自己的朝向（flipX）记录，开始时朝向可见，所以也在支撑里。
- **要留意的两处**：(1) Clapper 闪到背后 6 u 内有墙时接 `Escape Jump`（跳砸 / 跳施法，2 格、瞄你前 5 u）：这条链在表里（`Escape Jump` 是决策状态），口袋规则（forum.md §10.4）照旧。(2) Reed 举盾后**被打中**的反击（2 格连段，可拼刀）：这是打中触发的，支撑里有（RE_DEFEND 的模板含 `Parry Slash`），但规划器要知道"向举盾中的 Reed 出刀 = 触发反击"，见 3.2。
- 没有发现"动作触发、支撑里没有"的漏洞。

### 3.2 预测与规划：反应分支（只进 J / P，不进 S）

闪不闪是候选计划自己决定的，和命中效果分支同类。建议：

1. **静态数据** `reactive_triggers.json`（从本文 §1.2 的表生成，`reactive.py` 的 `RANGES` + FSM 解码）：每类每个机制的源状态、触发形状（相对 transform，盒 / 圆并集，四周 +0.05 u）、门槛（Reed 上膛：`Defend Start` / `Stab Antic` 开、`Evade Antic` 关；`Just Did Defend`；Bellbearer 冷却：`Evade` 开、`Throw Antic` 关，`In Range` ≥ 0.5 s，背后 3 u 无墙；Clapper `Idle` ≥ 0.25 s；Minister 只在 `Evade?`；Choristor `Hop Check` 的公式）、隐藏硬币（Clapper `Will Evade`、Reed `Will Defend`：0.5，**同一次访问里你已在盒内且门槛开着而它没反应，就说明硬币是反面，本次 p = 0**）、延迟（同帧至 1 帧，含"它进源状态那一帧就检查"）、起手和运动模板（就是行为表里该家族的按状态模板）。
2. **EnemyTracker 维护门槛状态**：都能从看得见的事件推出（上一次举盾 / 突刺 / 扔铃 / 闪避、进当前状态的时刻），视觉路径同样可用（M3 的可观测阶段表要包括这些状态）。
3. **反应分支**：对阶段 2 的每一行（已做包络的候选），沿它的主角物理盒轨迹找每个"在源状态（或即将回到源状态）、门槛开"的敌人第一次进盒的步 t_e（敌人位置用它当前状态的外推；它从 `Defend End` / `Stab Recover` / `Throw Recover` 等回到 `Alert` 的那一帧也是机会）；以 p 在 t_e（至多 + 1 帧）把该敌人切到闪身模板（起手 + 背离**起跳时**主角的位移），1 − p 保持原预测。p（R0 每次访问）：Reed 闪避 ≈ 0.95（你在它 `Alert` 期间进盒）/ ≈ 0.8（它回到 `Alert` 时你已在盒里），Reed 举盾 ≈ 0.45，Bellbearer ≈ 0.97，Clapper ≈ 0.49，Minister 0.485。J 里对该敌人的命中按两支加权：`hits_k = (1 − p)·hits_nominal + p·hits_dodge`。上限像命中效果一样（每 tick 前 K 行、每行最多 2 个敌人）。属性测试：S、Hz、U 与关掉反应分支时逐位相同。
4. **J 会变的地方**：
   - **冲刺斩的期望伤害**：Reed / Bellbearer 门槛开着时，冲刺途中（冲刺斩前）就进盒 → 0.133 / 0.083 s 后它以 30 / 32 u/s 离开，冲刺斩落空；进盒的那一步就是冲刺斩开始（刀 0.12–0.13 s 到）→ 刀先到。冲刺斩打 Reed：带反应时 43 %、不带时 76 %（§2.5）。
   - **打空窗（诱闪再打）**：Reed 闪过一次就"没子弹"，直到它下一次举盾或突刺；Bellbearer 闪过一次要等它下一次扔铃。这段时间里冲过去不会被闪掉——这是冲刺斩 / 飞针打这两类的最好时机。诱的方法就是让身体进一下盒（Reed 的盒在它正下方 ±1.5 u 一整条、同高到上方 ±3.8 u；Bellbearer ±3.3 u）再退出。Clapper：在 Slam Range 里待到它 `Idle` 0.25 s，硬币正面就闪；闪完 `After Scuttle` 你还在范围里它**只会锤或施法**（不会再闪），所以追上去是危险的，不是空窗。Minister 的闪避只在它出完招之后、你在 4.95 u 内时（50 %），闪完 6.5 u 外回 `Chase`，没有空窗价值。
   - **别撞盾**：Reed `Alert` 里、`Just Did Defend` 为假时，你进 7.65 u 就有约一半的机会它举盾（同时在已上膛的 Evade Range 里就是闪）；对举盾的 Reed 出刀 → `BLOCKED HIT` → 2 格连段反击。打分里把"向可能举盾的 Reed 冲刺斩"的期望伤害和反击风险（P）算进去。
   - **拼刀时机**：闪身状态都没有攻击碰撞体，没有可拼的东西；Reed 举盾后的反击可拼（parry 5，forum.md §12.4），R8 的拼刀分支照旧。
5. **打中触发的反应**（§0 第 4 点）属于命中效果分支：候选的刀在 t 打中 → 该敌人按 FSM 的被打中出边切换。Clapper 要按"打中时它在 `Idle` 里待了多久、硬币亮没亮"分：`Idle` < 0.25 s（硬币未亮）→ 打中把 0.5 的硬币换成 `Close Range` 的约 1/3（实测 0.25）；硬币已亮出反面 → 打中把 0 变成约 0.2；你在盒外 → `Far Range`（几乎不闪）。也就是说"打一刀 `Idle` 的 Clapper 让它更容易闪"只在后一种情形成立，前一种情形打它反而让它少闪、多出锤 / 施法（`Close Range` 扣掉回 `Idle` 的，约 2/3 立刻出锤或施法，该进 P）。Reed `Alert` → `Stab Pos`；Minister / Maestro 下一招提前；Envoy 冲锋。支撑本来就含这些后继；要改的只是打分。

**归属**：反应分支和门槛跟踪放 **R5**（它的第一项"决策的感知时刻"就是同一份 FSM 静态提取：每个决策读主角位置的动作在哪个状态、是每帧还是只在进入时——这里的结论：Reed `Alert`、Bellbearer `In Range`、Clapper `Idle` 每帧读，含进入当帧；Choristor `Hop Antic` 只在进入那一帧读；`Hop Check`、Minister `Evade?`、Clapper `Close Range` 是瞬时决策），只改 J / P；"诱闪再打""打空窗"作为 **R6** BAIT / FOCUS 的目标；冲刺斩原语本身（`M_DASH_STAB`）在 **R7**；举盾反击的拼刀在 **R8**。R3 的命中效果分支扩到敌人一侧（打中触发的出边，Clapper 按上面第 5 点分情形）。

### 3.3 行为表的协变量（"主角当前动作"）【录】

在每个决策状态的出边上，基线 = P(下一状态 | |dx| 档 0/3/6/10 u、高度档、左右)（向边际平滑，α 1），候选 = 再加主角当前动作组（冲刺斩 / 飞针 / 冲刺 / 出刀 / 无），**逐级回退**到基线那一格（α 16），按场 2 折留出对数损失（`covariate_test`）。第一版把候选格直接向边际平滑（稀疏的动作格被拉向边际，偏向不利于候选），那一版的数字留在 `gain_v3_marginal_smoothing`：

| 数据 | 决策状态数 / 决策数 | 加权平均增益（nats / 决策；第一版） | 增益 ≥ 0.01 的状态 |
|---|---|---|---|
| R0 | 29 / 263,543 | +0.0031（−0.0003） | Clapper `Idle` +0.014、Minister `Chase` +0.013、Minister `Retreat?` +0.018 |
| R1 | 27 / 61,071 | −0.0008（−0.0038） | Reed `Alert` +0.012、Clapper `Idle` +0.015（区间含 0）、Minister `Chase` +0.017、Minister `Retreat?` +0.030 |
| 你 | 24 / 16,504 | +0.0033（−0.0191） | Choristor `Unalert Tick?` +0.021、Choristor `Attack Choice` +0.015、Reed `Alert` +0.018、Minister `Chase` +0.016 |

总增益在 ±0.003 nats / 决策，可以忽略。变好的多半是有"被打中"出边的状态（Clapper `Idle → Dmg Attack`、Minister `Chase` / `Retreat? → Range Check`、Reed `Alert → Stab Pos`）：出刀预测"马上会被打中"。**建议不把主角动作加进行为表**；要加的是 (1) "主角身体在某个触发盒里"（精确几何，替代这些状态的距离分档：Minister `Evade?` 在盒内 0.485、盒外 0；Choristor `Hop Check` 用公式），(2) "刚被打中"（区分被打中出边；规划器里由命中分支提供）。这两个都是视觉可得的。

### 3.4 实机探针（写好、没跑）

`C:\ssbot\sandbox\reactive_scripts\probe_dash_stab.py`：从波次起点存档（默认 `fo_r1_w8`：两只 Reed + Bellbearer）对指定类型的敌人做冲刺斩（按住冲刺、冲刺后 `--attack-delay` 秒按攻击，出 Reaper 的 Dash Upper），每次记录 1.2 s 的主角与目标逐帧状态和事件，离线算"进盒帧、闪身帧、命中帧"。目的：给 3.2 的冲刺斩期望伤害一个按"进盒时刻 − 冲刺斩开始"分档的命中率（你的 329 次里 Reed 只有 86 次、带反应 23 次），核对 Reed 上膛 / 未上膛时的差别，并直接看一次"往前闪"是哪一种。需要一个空闲实例，读档、会抢焦点。

---

## 4. 没弄清的

1. 冲刺斩打闪身的精确时间窗（3.4 的探针）；bot 自己的数据几乎没有冲刺斩（R1 的 DASH_IN 没出冲刺斩，§0 第 7 点）。
2. Reed 已上膛、身体在盒内但这次 `Alert` 没闪：你在它 `Alert` 期间进盒时 3–9 %，它回到 `Alert` 时你已在盒里时 16–25 %（R0 / R1）。被打中抢先之外的部分没有逐个查【推：重新打开的 Evade Range 要到下一个物理步才登记已在里面的主角；或同一帧 `Choice` 计时到期】。
3. 盒外的闪避 / 举盾大多在波次刷出后第一次进 `Alert` / `In Range` 时（R0 Reed 闪避 15 / 21、举盾 16 / 31、Bellbearer 32 / 49）。Bellbearer 的盒外事件 45 / 49 有另一只同名 Bellbearer 同一帧也在 `Evade Antic`，但 46 / 49 主角也不在另一只的盒里：刷出时的触发器状态、导出把同名实体串了，还是真有联动，未查清（实机看一次两只同时刷出时的 `fsm` 事件和触发器内容即可）。
4. Clawmaiden 的 `Tele Escape Range`（2.66 u）在 3 份数据里一次都没触发：她瞬移落点离主角有下限，主角很少正好站进去。
5. （已解决）第一版"Clapper 冲刺组 `Idle` 闪避偏低（R0 0.32）"是漏算 0 帧 / 同帧连跳的访问造成的，重算后 0.43、区间重叠。

## 5. 复现

```
# 静态（离线 UnityPy，低优先级）
C:\ssbot\sandbox\reactive_scripts\run.cmd dump_enemies.py C:/ssbot/sandbox/reactive_scripts/out
C:\ssbot\sandbox\reactive_scripts\run.cmd compress.py
C:\ssbot\sandbox\reactive_scripts\run.cmd ranges.py
C:\ssbot\sandbox\reactive_scripts\run.cmd layers.py
C:\ssbot\sandbox\reactive_scripts\run.cmd hero_layers.py
C:\ssbot\sandbox\reactive_scripts\run.cmd st.py Song_Reed 0 Alert,Evade_Antic,Evade,Evade_End,Defend_Start
# 录像（brain 目录，低优先级，NUMBA_NUM_THREADS=4）
cd brain
..\scripts\uv.cmd run python -m ssbot.tools.forum_extract <R1 运行目录 ...> --out C:/ssbot/sandbox/reactive_scripts/cache_r1
..\scripts\uv.cmd run python -m ssbot.tools.forum_demo C:/ssbot/data/human/20261004_002749 C:/ssbot/data/human/20261004_012300 C:/ssbot/data/human/20261004_091214 C:/ssbot/data/human/20261004_133855 --cache C:/ssbot/sandbox/reactive_scripts/demo_cache --json C:/ssbot/sandbox/reactive_scripts/demo_cache/demo.json
..\scripts\uv.cmd run python C:/ssbot/sandbox/reactive_scripts/reactive.py --out C:/ssbot/sandbox/reactive_scripts/reactive_full4.json
..\scripts\uv.cmd run python C:/ssbot/sandbox/reactive_scripts/bell_swap.py
..\scripts\uv.cmd run python C:/ssbot/sandbox/reactive_scripts/outliers.py
```

R1 抽取用的运行：`20261004_105441_Forum_A_w3_mix_data2`、`110245_*`（2 个）、`111158_*`（2 个）、`130403_*`（2 个）、`131323_*`（2 个）、`143803_*`（2 个）、`153511_Forum_A_w7_mix_data2`、`144623_Forum_A_w7_mix_data_idle_oracle`（可读的 218 局；2× 和当时可能还在写的 `1546xx`、`155649` 没用）。`reactive.py` 全部约 15 min（R0 7 min、R1 4 min、人 3 min）。第一版 `reactive_v3.py` → `reactive_full3.json` 保留作对照；`bell_swap.py` / `outliers.py` 读的是 `reactive_full3.events.json`（Bellbearer 的事件两版相同）。
