# Forum 敌人在冲刺斩前的"闪身"：是招还是走动，由大黄蜂的什么决定（PC 1.0.30000）

**问题（你，2026-10-04）：** "有时候冲刺斩快打中的时候怪会往后或者往前闪一下，这个动作是一招吗？还是就是普通移动？这个闪身绝对是由大黄蜂动作决定的。"

**标签：** 【包】离线 UnityPy 读训练副本场景包 `hang_04_boss.bundle`、`globalgamemanagers`（层矩阵）、主角预制体包（只读）；【码】反编译 1.0.30000 C#（`C:\ssbot\decomp\1.0.30000`）；【录】录像统计（下面"数据"）；【推】由代码或数据推出、未单独实测。没有连接任何游戏实例。

**数据：** R0 = 随机数据策略的 142 场完整连战（`C:\ssbot\data\m2_forum_r0\cache` 107 场 + `cache_fresh` 35 场）；R1 = 定点采集 data2 / idle 策略的 218 局波次起点（`20261004_105441` … `153511`、`144623`，本次用 `forum_extract` 抽到 `C:\ssbot\sandbox\reactive_scripts\cache_r1`）；人 = 你的 4 段录像（`20261004_002749`、`012300`、`091214`、`133855`，58 次尝试，`forum_demo` 扫描）。

**脚本与原始输出：** `C:\ssbot\sandbox\reactive_scripts\`：`dump_enemies.py` → `out\*.txt`（每类一只的全部子物体、层、碰撞体、触发器组件和全部 PlayMaker FSM 逐动作解码）、`ranges.py` → `out\ranges.json`（每个实例的每个 AlertRange 的世界形状）、`layers.py`（层矩阵）、`hero_layers.py`（主角哪些碰撞体能被 Hero Detector 看见）、`st.py` / `line_state.py`（查状态）、`reactive.py` → `reactive_full3.json`（+ `.events.json`，录像统计，本文的数字）、`outliers.py`（触发器外的事件逐个查）、`probe_dash_stab.py`（**写好、没跑**的实机探针，§3.4）。复现见 §5。

---

## 0. 摘要（可直接转述）

1. **是招，不是普通走动。** Forum 里会"闪"的都有专门的 FSM 状态：先一个很短的起手，再按自己的朝向用固定速度往后蹿（Reed `Evade Antic → Evade` 0.133 s 后 30 u/s，退约 4.9 u；Choir Bellbearer 0.083 s 后 32 u/s，约 5 u；Minister 0.1 s 后 25 u/s，约 6.5 u；Choir Clapper `Evade Scuttle` 立刻 15 u/s 退 0.35 s，约 5.4 u；Clawmaiden `Tele Out Antic` 0.183 s 后瞬移）【包】【录】。另外两种看起来像"闪"的：**Choristor 的跳步**（`Hop Back` / `Hop Forward`，12 u/s 一跳约 2 u，连跳 1–3 下）是它两招之间的走位方式；**Reed 的 `Defend Start`** 是举盾姿态，起手时朝你飞近约 1 u（这就是"往前闪"的那一种），之后打到盾上会被 2 格的连段反击。
2. **你说得对：是大黄蜂决定的——但决定它的是你的身体到了哪里，不是你按了攻击。** 所有这些"闪"的感知都是挂在敌人身上的触发盒（`AlertRange`，第 13 层 Hero Detector）；第 13 层只和第 9 层 Player 碰撞，第 9 层上带碰撞体的只有主角本体那个 0.5 × 2.08 的物理盒。主角的刀（第 17 层 Attack）、受伤盒（第 20 层 Hero Box）碰不到这些触发盒；Forum 敌人身上也没有 Attack Detector（第 31 层）【包】。所以冲刺 / 冲刺斩引发闪身，是因为冲刺（28 u/s）和收割者冲刺斩的前冲（50 u/s 起、每步 ×0.85，约 6.7 u）在零点几秒里把你的身体送进了它的触发盒，它在**下一帧**就开始闪【包】【码】【录】。
3. **录像核对：位置一项就够，动作不加信息。** 5 种"进盒就闪"的机制，事件发生时主角身体都在触发盒里：Clapper 4999 / 4999、Reed 闪避 1195 / 1195、Reed 举盾 960 / 960、Bellbearer 4468 / 4517（剩下 49 次里 48 次是另一只同名 Bellbearer 同一帧也在闪，怀疑导出把同名实体串了，未查清）（R0；R1、你的录像同样几乎全在盒里）。按"这一轮里你的身体第一次进盒（门槛已开）时你在干什么"分组，之后闪不闪的比例基本一样：Bellbearer 无动作 0.97 / 出刀 0.97 / 冲刺 0.99；Clapper 0.48 / 0.46 / 0.32（它每次 Idle 先抛一枚 50 % 的硬币）；Minister 在盒里 0.485、盒外 0（2621 / 2870 次决策）；Choristor 跳的方向按"距离 ≤ 6–10 u 的随机数就往后跳"的公式算出的概率和实际**逐组相等**（你的冲刺斩之后：实际 0.523，公式 0.530）。决策表加"主角当前动作"作协变量，留出对数损失**没有改善**（R0 −0.0003、R1 −0.004、你的录像 −0.019 nats / 决策）；唯一变好的是 Clapper `Idle`（+0.012 / +0.064），原因是那里有一条"被打中"出边（见第 4 点）【录】。
4. **真正"由动作决定"的是打中之后的反应**（要先打中）：Clapper 在 `Idle` 被打中 → `Dmg Attack` → 你在锤的范围里就进 `Close Range` → 1/3 概率 `Evade Scuttle`（R0 被打中后的 1705 次里 403 次闪，23.6 %；平时走过来时 7.0 %）；Reed 在 `Alert` 被打中 → `Stab Pos`（转头刺你），在 `Stab Pos` 再被打中 → 立刻 `Stab Antic`；Minister 被打中 → 下一招提前（攻击计时截到 ≤ 0.5 s）；Maestro 被打中 → 立刻进入下一次出招选择；Envoy 走路时被打中 → 冲锋。打中的来源可以是任何人（Garmond、Cogfly 也算）【包】【录】。
5. **你最可能看到的是谁：** 你的 329 次冲刺斩（Reaper 257、Wanderer 72）里，前方 8 u 内最近的敌人：Choristor 137 次（其中 62 次在 −0.1…+0.6 s 内跳了一步，58 次往后）、Reed 86 次（23 次：举盾 17、闪避 6）、Clapper 36 次（闪 9 次）。**往后或往前的快速一闪，最可能是 Choristor 的跳步和 Reed（往后闪避 / 往前举盾）。** 区别：Choristor 不管你干什么都在跳，方向只看距离；Reed 的闪避和举盾是你的身体进了它的盒子才触发的。冲刺斩的第一下在冲刺斩动画开始后 0.117–0.133 s 打中（p5–p50）；Reed 从你进盒到真正开始移动要 1 帧 + 0.133 s，所以在冲刺斩开始时才进盒，往往是刀先到（Reed 闪避 6 次：先打中 3、先闪 1、没打中 2）；进盒早（冲刺途中）就闪掉了。Reed 带着反应动作时你的冲刺斩只打中 10 / 23（43 %），没有时 48 / 63（76 %）【录】。
6. **对 bot：** (a) **安全不受影响**：这些闪身都已在支撑里（行为表从 `Alert` / `In Range` / `Idle` / `Evade?` / `Hop Check` 都记录了这些后继，停留下限正好等于 FSM 的门槛：Bellbearer 0.508 s、Clapper 0.250 s、Reed 0），本身没有攻击碰撞体，只有身体伤害；约 10 % 的 Reed 闪避、2–3 % 的 Bellbearer / Minister 闪避和 Choristor 后跳是**朝你那一侧**退的（Clapper 几乎没有）（你冲过它身后、它还没转身），模板按它自己的朝向记录，所以也在支撑里。(b) **预测 / 规划要改的是打分**：闪不闪是"候选计划的身体轨迹第一次进它的触发盒"的确定函数（加几枚看得见或可推断的门槛和硬币），建议在 MultiForecast 的打分里加一个"反应分支"（只进 J / P，不进 S）：候选在 t 进盒 → 以 p（门槛开时 Reed / Bellbearer ≈ 1、Clapper 0.5、Minister 0.5）在 t + 1 帧进入闪身，冲刺斩的命中按闪开后的位置算。它也给出两种打法：**趁它"子弹打空"时冲**（Reed 闪过一次后，要等下一次举盾或突刺才会再闪；Bellbearer 闪过一次后，要等下一次扔铃）、**别在 7.65 u 内对着可能举盾的 Reed 冲**（会撞盾吃 2 格反击）。归属：R5（和"决策的感知时刻"是同一份 FSM 静态提取），诱闪 / 打空窗在 R6，冲刺斩原语在 R7。(c) **行为表不加"主角动作"**；要加就加"主角身体在某个触发盒里"这个精确几何量（Minister `Evade?` 在盒内 0.485 / 盒外 0，比距离分档干净得多），以及"刚被打中"（打中分支已能算）。
7. **顺带发现：** R1 定点采集的 DASH_IN 战术 218 局里**一次冲刺斩都没打出来**（`Dash Upper` 片段 0 次；R0 随机策略 142 场 19 次；你的录像 329 次）：它在按冲刺后 0.04–0.14 s 按攻击，落在 0.1 s 的冲刺本身里，出的是普通横斩；冲刺斩要在冲刺后的 sprint 里按攻击【码 `forum_policy.py` 376–398】【录】。R7 要冲刺斩数据前先改这里。

---

## 1. 静态：每类敌人的"闪身"状态和进入条件

### 1.1 敌人能"感知"大黄蜂的哪些东西【包】【码】

- 9 类 Forum 敌人的控制 FSM 里，读主角的方式只有：`CheckAlertRangeByName` / `CheckAlertRange`（触发盒里有没有主角）、`GetDistance` / `GetXDistance`（transform 距离）、`FaceObjectV2` / `CheckPassedTarget` / `CheckTargetDirection`（相对位置）、HealthManager 发来的 `TOOK DAMAGE` / `BLOCKED HIT` / `HIT`（**打中之后**才有，`HealthManager.cs` 793–1091 行）、`CheckHeroPerformanceRegion`（主角在弹琴 Needolin，进 `Sing`），以及 Clawmaiden `Spin Antic` 读 PlayerData `silk`（主角丝量）。多段攻击的 `hornet_multi_wounder` 子 FSM 读 `cState.parrying` 和 `CanHeroTakeDamage`，只管连段本身。**没有任何动作读主角是否在出刀、冲刺、飞针、跳或按键**；全局转移里也没有这类事件（各类的全局转移只有 `ZERO HP`、`CALL`、`MULTI HIT CONNECT`、`GO UP/LEFT/...`）。
- 所有范围都是 `AlertRange : TrackTriggerObjects`，挂在第 13 层 `Hero Detector`、`ignoreLayers` 0、无标签过滤。层矩阵（`globalgamemanagers` Physics2DSettings）：13 层只和 3、6、9 层相碰；主角预制体和全部纹章包里，3 / 6 / 9 层上带碰撞体的只有 `Hero_Hornet` 根的 BoxCollider2D（0.5 × 2.079，非触发器，即 STATE `hero.box`）。主角攻击在 17 层、受伤盒在 20 层，都碰不到 13 层。Forum 敌人身上没有 31 层（Attack Detector，会和 17 层相碰）的子物体【包 `layers.py`、`hero_layers.py`、`dump_enemies.py`】。
- 触发盒按物理步更新（`OnTriggerEnter2D`），FSM 在 `Update` 里每帧查（`everyFrame=1` 的地方）：所以从身体进盒到状态切换是 0–1 个物理步 + 1 帧【码 `TrackTriggerObjects.cs` 168–236、`CheckAlertRangeByName.cs`】。`lineOfSight = Parent` 的盒子另要求敌人到主角之间没有地形（Forum 场地内几乎总成立）【码 `AlertRange.cs`】。

### 1.2 每类的状态、触发、门槛

形状是相对敌人 transform 的世界尺寸（含根缩放；`ranges.py`）。"能改变它的"一栏：**位** = 只通过主角身体的位置；**中** = 要先打中（任何来源）；**无** = 与主角无关。

| 类型 | 会"闪"的状态（家族） | 怎么进去（源状态 → 条件） | 门槛 / 冷却 / 随机 | 运动 | 能改变它的 |
|---|---|---|---|---|---|
| **Choir Clapper** | `Evade Scuttle`（CC_EVADE） | ① `Idle`：每帧 `Will Evade ∧ 主角在 Slam Range ∧ Can Evade` → EVADE。Slam Range = 盒 x ±8.049、y −0.543 ± 3.913（站地时世界 y ≤ 10.82） | `Will Evade` 每次进 `Idle` 抛一次（RandomBool 50 %）；`Can Evade` 进 `Idle` 0.25 s 后才真 | 先 `FaceObjectV2`（两次转身至少隔 0.5 s），`SetVelocityByScale +15`（背离朝向）0.35 s；背后 6 u 内有墙 → `Escape Jump` → 跳砸 / 跳施法 | 位 |
| | | ② `Close Range`（从 `Walk` 的 CLOSE、`After Scuttle`、`Dmg Attack` 来）：SendRandomEventV4 SLAM / EVADE / CAST 各 1/3（eventMax 1、missedMax 3） | 刚闪过（`Evaded`，到下一次出招才清）只在 SLAM / CAST 里选；正在后退走（片段 `Walk B`）→ 直接 SLAM；另一只在出招 → 回 `Idle` | 同上 | 位；经 `Dmg Attack` 来时是中 |
| | | ③ `Idle` 另一只 Clapper 在 4 u 内 → `Avoid Type`：主角和它在同一侧 → EVADE，否则 → `Walk` | — | 同上 | 位（相对另一只） |
| | | ④ `Idle` 被打中（`TOOK DAMAGE`）→ `Dmg Attack` → 主角在 Slam Range → `Close Range`（再按 ②），否则 `Far Range` | — | — | **中** |
| **Clawmaiden** | `Tele Out Antic`（CM_TELE）：瞬移 | ① 瞬移刚落地的 `Tele In End`：每帧主角在 `Tele Escape Range`（圆 r 2.66）→ ESCAPE，马上再瞬移；② `Fly`：距离 > 20 → TELEPORT；③ `Fly` 等 1–2 s 后 `Tele?`：距离 > 22 → TELEPORT，否则 V4 50 / 50 | — | `Tele Out Antic` 0.183 s 后消失，在 `Teleplane` 里随机落点（离主角在一个区间内、离自己 ≥ 4 u） | 位 |
| **Minister** | `Evade Antic → Evade`（MI_EVADE） | ① `Evade?`（出现在 `Attack End`、`Parry Stance End`、`Parry Slash End` 之后，瞬时）：V4 50 % 直接 `Retreat?`；另 50 % 主角在 `Evade Range`（圆 r 4.955，圆心在 transform 下方 1 u）→ EVADE；② 它自己的连斩连上之后（`Multihit → Reset Z Pos`）→ 必定 `Evade Antic` | 只在自己出招之后；不会在 `Chase` 里闪 | `Evade Antic` 0.1 s → `Evade`：`SetVelocityByScale +25`、y +5，DecelerateXY 0.95 / 0.975 | 位（①）；② 是它打中你 |
| | `Parry Stance`（MI_PARRY，举刀格挡） | `Chase` 攻击计时到且主角在 `Attack Range`（圆 r 7）→ `Attack Choice` V4 CHARGE / PARRY 1:1 | — | 在姿态里飞到离主角 6 u；**被打中**（`BLOCKED HIT`）→ 4 段反击 | 位；反击是中 |
| | （被打中） | `Chase` / `Retreat?` 被打中 → `Range Check`：攻击计时截到 ≤ 0.5 s | — | — | 中 |
| **Maestro** | 无闪避；`Defend Start`（MA_DEFEND）是召小机械围成防阵 | `Attack Choice` V4 FIRE / DEFEND 0.75 / 0.25 | — | 原地 | 无；`Fly` / `Forum Fly` 被打中 → 立刻 `Summon?`（中） |
| **Tiny** | 无；`Defend Ready` 由 Maestro 的事件指挥 | Maestro 发 `DEFEND READY` | — | — | 无（控制 FSM 没有被打中出边） |
| **Reed** | `Evade Antic → Evade`（RE_EVADE） | `Alert`：每帧主角在 `Evade Range` → EVADE。**Evade Range 是两个盒子的并集**：x ±1.479、y +0.043 ± 5.202（它正下方 / 正上方的竖条）和 x ±3.810、y +2.570 ± 2.674（与它同高到上方 5 u 的横条） | **一发子弹**：进 `Evade Antic` 时把 Evade Range 关掉，到下一次 `Defend Start` 或 `Stab Antic` 才重新打开 | `Evade Antic` 0.133 s → `Evade`：`SetVelocityByScale +30`、y +5；`Evade End` 50 % 回 `Alert`，否则在投掷范围内就扔针（`Evade End` 的 STAB 检查用的是已关掉的 Evade Range，永远不发） | 位 |
| | `Defend Start → Defend`（RE_DEFEND，举盾） | `Alert`：每帧 `Will Defend ∧ 主角在 Defend Range（圆 r 7.65）∧ ¬Just Did Defend` → DEFEND；Alert 里 EVADE 的检查排在 DEFEND 前面 | `Will Defend` 每次进 `Alert` 抛一次（50 %）；`Just Did Defend` 举过盾后为真，到下一次 `Stab Antic` / `Throw Antic` 才清 | `Defend Start` 0.083 s，飞到离主角 3 u（多半是**朝你**：68–72 % 的起手位移朝你一侧）；被打中（`BLOCKED HIT`）→ `Block → Parry Y Aim → Parry Slash`（多段，整链 2 格，可拼刀） | 位；反击是中 |
| | （被打中） | `Alert` 被打中 → `Stab Pos`（飞到 5 u、主角进 Stab Range 就刺）；`Stab Pos` 再被打中 → 立刻 `Stab Antic` | — | — | 中 |
| **Envoy** | 无 | — | — | — | `Walker` 被打中 → `Leader?` → `Charge Antic`；`Charge` 被打中 → `Reset`（继续冲） |
| **Choristor** | `Hop Back` / `Hop Forward`（在 CH_IDLE 里，走位） | `Battle Idle` 0.2–0.3 s → `Move Start`（连跳 1–3 下、Hop Distance ~ U(6, 10)）→ `Hop Antic`（**进入那一帧**主角在 `Close Range`（盒 x ±2.885、y −0.27 ± 1.906）→ 直接去出招）→ `Hop Check`：\|x 距离\| ≤ Hop Distance → `Hop Back`，否则 `Hop Forward`；`Slash Check` 脚下前方没地 → `Cancel To Hop Back` | Hop Distance 每次 `Move Start` 抽一次 | `SetVelocityByScale ±12`，一跳 0.15 s 约 2 u；落地数跳数，跳完去 `Attack Choice` | 位 |
| **Choir Bellbearer** | `Evade Antic → Evade`（CB_EVADE） | `In Range`：每帧 `主角在 Evade Range（盒 x ±3.297、y ±6.659）∧ 背后 3 u 内没有墙（射线）∧ Can Evade ∧ ¬Evade Cooldown` → EVADE；`Out of Range` 主角回到投掷范围时的 `Insta Throw?` 同样检查一次 | `Can Evade` 进 `In Range` 0.5 s 后才真；`Evade Cooldown` 在 `Evade` 置真、下一次 `Throw Antic` 才清（**一发子弹**，扔一次铃补一发） | `Evade Antic` 0.083 s → `Evade`：`SetVelocityByScale +32`、y −8 | 位 |

几个细节【包】：`SetVelocityByScale` 的正数是"背离朝向"（这些精灵默认朝左：Clapper 的锤冲 −30 是往前，forum.md §10.1）；进闪身状态时的 `FaceObjectV2` 两次转身至少隔 0.5 s，所以你刚冲过它身后时，它可能还朝着旧方向，"往后退"就退向你这一侧（§2.4 的"朝你一侧"比例）。Bellbearer 的模板 FSM `FSM`（`FLYER RESPONSE`、`GO UP/DOWN/LEFT/RIGHT`）只是飞行物互相推开，和主角无关。

### 1.3 和行为表的关系

`gauntlet_tables.FORUM_SPECS` 已把 `Evade Scuttle`、三个 `Evade Antic`、`Tele Out Antic`、`Defend Start`、`Parry Stance Antic` 当作家族的开始状态，`Hop Back` / `Hop Forward` 在 Choristor 的决策状态里（CH_IDLE）。表里的停留下限正好是 FSM 的门槛【录 `knowledge/.../forum/*.json` 的 `dwell_s.<源状态>.by_successor`】：Bellbearer `In Range → Evade Antic` 最短 0.508 s（门槛 0.5 s）、Clapper `Idle → Evade Scuttle` 0.2498 s（0.25 s）、`Idle → Dmg Attack` 0.0167 s（被打中随时）、Reed `Alert → Evade Antic` 0（`Alert` 里随时）。

---

## 2. 录像

方法（`reactive.py`）：每个敌人一条按帧的状态序列（控制 FSM），每帧的主角物理盒（STATE `hero.box`），按 §1.2 的形状算"身体在不在盒里"（盒子四周放宽 0.05 u：20 场里 1445 次事件有 73 次离精确形状 0–0.05 u，0.05–0.3 u 之间 0 次；推测是 transform 位置和物理步位置差一帧）。事件 = 控制 FSM 事件里**从源状态直接**进入闪身（例如 `Idle → Avoid Type → Evade Scuttle` 和 `Idle → Dmg Attack → Close Range → Evade Scuttle` 不算 `Idle` 的进盒闪避，单独计）。主角的动作按动画片段分：冲刺斩（`Dash Upper*`、`Wanderer Dash Attack*`）、飞针（`Harpoon*`）、冲刺（`Dash*`、`Air Dash`、`Sprint*`）、出刀（片段名含 `Slash` / `DownSpike`），"当时的动作" = 该帧和之前 0.2 s 里有没有（优先级按这个顺序），否则"无"。门槛按 §1.2 跟踪（Reed 的一发子弹和 `Just Did Defend`、Bellbearer 的冷却和 0.5 s、Clapper 的 0.25 s）；Clapper 的 `Will Evade` 和 Reed 的 `Will Defend` 看不见。

### 2.1 事件是不是都发生在身体进盒时【录】

| 机制 | R0 事件 | 其中身体在盒内 | R1 | 你 |
|---|---|---|---|---|
| Clapper `Idle → Evade Scuttle` | 4999 | 4999 | 549 / 549 | 51 / 51 |
| Reed `Alert → Evade Antic` | 1195 | 1195（且 Evade Range 已上膛 1195） | 420 / 420 | 130 / 130 |
| Reed `Alert → Defend Start` | 960 | 960 | 417 / 417 | 127 / 127 |
| Bellbearer `In Range → Evade Antic` | 4517 | 4468 | 418 / 425 | 141 / 143 |
| Clawmaiden `Tele In End → Tele Out Antic` | 0（你进它 2.66 u 圈的情形没出现过） | — | 0 | 0 |

Bellbearer 盒外的 49 次（R0，已放宽 0.05 u）：1 次离盒边 ≤ 0.2 u；其余 48 次都发生在**另一只 Bellbearer 同时也在 `Evade Antic`** 的时候（两只同时"闪"，主角那一帧不在任何一只的盒里），46 次另一只就在这只的 Evade Range 里。敌人在第 11 层，碰不到 13 层；两只同名（`Pilgrim 03 Song`）的实体，怀疑是导出把同名实体的 FSM 状态串了，或者有我没找到的联动，未查清（R0 4517 次里 1.1 %）【录 `outliers.py`、`bell_swap.py`】。

`Idle` 被打中后的闪避（不算在上表）：R0 356 + 42 次（`Dmg Attack → Close Range → Evade Scuttle` / 经 `Avoid Type`），R1 16、你 23。

### 2.2 动作会不会改变"进盒后闪不闪"【录】

按"这一轮源状态里，身体第一次在盒内且门槛已开的那一帧"主角在干什么分组，之后在这一轮里闪了的比例（Wilson 95 % 区间）：

| 机制 | 数据 | 无动作 | 出刀 | 冲刺 | 冲刺斩 / 飞针 |
|---|---|---|---|---|---|
| Bellbearer 闪避 | R0 | 0.974（3372） | 0.970（786） | 0.990（391） | 冲刺斩 1 / 1 |
| | R1 | 0.983（297） | 1.0（63） | 0.978（46） | 飞针 0.94（16） |
| | 你 | 0.962（53） | 0.985（68） | 1.0（19） | 冲刺斩 3 / 3 |
| Clapper `Idle` 闪避（硬币 0.5） | R0 | 0.480 [0.469, 0.490]（8601） | 0.456 [0.434, 0.479]（1826） | 0.318 [0.245, 0.402]（132） | — |
| | R1 | 0.444（1122） | 0.529（68） | 0.517（29） | — |
| | 你 | 0.456（57） | 0.458（24） | 0.476（21） | 冲刺斩 4 / 5 |
| Reed 闪避（已上膛） | R0 | 0.860 [0.837, 0.881]（957） | 0.797 [0.751, 0.836]（344） | 0.933 [0.869, 0.967]（105） | — |
| | R1 | 0.752（460） | 0.889（54） | 0.95（20） | 飞针 0.78（9） |
| | 你 | 0.896（67） | 0.672（61） | 0.909（22） | 冲刺斩 0.50（12） |
| Reed 举盾（¬Just Did Defend；硬币 0.5） | R0 | 0.286（2432） | 0.249（839） | 0.406（138） | — |
| | R1 | 0.268（1352） | 0.252（171） | 0.267（45） | — |
| | 你 | 0.271（166） | 0.213（174） | 0.507（71） | 冲刺斩 0.32（28） |

- Bellbearer 几乎是确定的（门槛开时进盒就闪），三组相同。
- Clapper 的比例就是那枚 50 % 的硬币；冲刺组在 R0 偏低（0.32，n 132），R1 和你的录像里不低（0.52、0.48），合起来 67 / 182 = 0.37。方向是"冲刺时**更少**闪"，不是更多【推：冲刺多是擦过盒子边一两步就出去，`lineOfSight = Parent` 的视线检查在进盒后的下一个物理步才更新，可能来不及】。
- Reed 闪避不是 1：同一帧还有别的出边会抢先——**被打中**会先进 `Stab Pos`（出刀组、冲刺斩组更低就是这个：你的冲刺斩组 6 / 12，其余多半是刀先到、Reed 转去刺你），其余【推】是同一帧的 `Choice` 计时到期等，未逐个查。
- Reed 举盾：硬币 0.5 × "EVADE 优先"：你已经站得很近（同时在 Evade Range 里）时它闪不举盾；从远处冲进来时先进 7.65 u 的 Defend Range、还没进 Evade Range，举盾的机会更大（R0、你的冲刺组 0.41 / 0.51）。这是进盒的先后顺序（位置），R1 的冲刺组就没有差别（0.27）【推】。

逐帧的分层检验（每帧"下一帧闪没闪"，按 |dx| 0.5 u × dy 1 u × 左右分层，Mantel–Haenszel 合并比值比，`reactive_full3.json` 的 `cmh_*`）会给冲刺组 1.4–2.4 倍（R0：Bellbearer 1.68 [1.17, 2.42]、Reed 闪避 2.37 [1.71, 3.28]、Reed 举盾 1.82 [1.36, 2.44]、Clapper 1.20 [0.88, 1.63]，都在"已进盒、门槛开"的层里）：那是计数方式造成的——闪避发生在进盒那一帧，移动快的主角在盒里的帧里"进盒帧"占的比例高。出刀组（主角多半站着）在同样的层里是 Clapper 1.00 [0.92, 1.08]、Reed 闪避 1.07 [0.91, 1.27]、Reed 举盾 0.86 [0.73, 1.01]、Bellbearer 0.86 [0.68, 1.08]。按"每一轮"算（上表）才是"动作会不会改变闪的概率"的正确问法。

**瞬时决策**（`reactive_full3.json` 的 `decisions`）：

- **Choristor `Hop Check`**：公式 P(往后) = clamp((10 − |dx|) / 4, 0, 1)（Hop Distance ~ U(6, 10)）和实际逐组相等：R0 无动作 0.462 / 0.457（实 / 算，n 6364）、出刀 0.557 / 0.546（2193）、冲刺 0.452 / 0.461（219）；R1 0.486 / 0.486、0.636 / 0.644、0.642 / 0.628；你的录像 无 0.325 / 0.321（1146）、出刀 0.476 / 0.471（826）、冲刺 0.223 / 0.222（373）、**冲刺斩 0.523 / 0.530（216）**。分层比值比（|dx| 1 u × dy × 是否在盒里）冲刺斩 1.02 [0.55, 1.91]、冲刺 1.00 [0.50, 2.02]（你）。
- **Minister `Evade?`**：盒内闪 1272 / 2621 = 0.485、盒外 0 / 2870（R0）；R1 404 / 854 = 0.473、0 / 500；你 35 / 70 = 0.50、0 / 107。出刀 / 冲刺组的比值比 0.90 [0.76, 1.06]（R0）、0.85 [0.55, 1.30]（R1）。
- **Clapper `Close Range`** 选 EVADE：从 `Walk` 来 814 / 11596 = 7.0 %（R0）、从 `Dmg Attack`（刚被打中）来 403 / 1705 = 23.6 %、从 `After Scuttle`（刚闪过）来 0 / 1265（`Evaded` 门槛）；R1 6.0 % / 21 % / 0、你 — / 21 % / 0。`Dmg Attack` 去 `Close Range` 当且仅当主角在 Slam Range（1705 / 1709；盒外 1856 / 1856 去 `Far Range`）。
- **Clapper `Avoid Type`**（主角和另一只同侧才闪）：R1 出刀组比值比 4.9 [2.5, 9.8]——分层里没有"另一只在哪边"，是混杂，不是因果（FSM 只读两个方向）。

### 2.3 反应延迟【录】

- **从身体进盒到状态切换**（门槛已开时）：Reed 闪避 p50 0.017 s（1 帧），p95 0.083（R0）/ 0.058 s（你）；Reed 举盾 1 帧，p95 0.033 s。Clapper 和 Bellbearer 的 p50 是 0.28 s 和 0.23–0.35 s：主角**已经**在盒里、它刚进 `Idle` / `In Range` 时要等 0.25 / 0.5 s 的门槛（Clapper p95 0.283 = 0.25 s + 2 帧）；门槛开着时进盒同样是 1 帧（p5 0.017 s）。
- **从你的动作开始到它切换**：分布很宽，因为取决于动作开始时离盒子多远：冲刺开始 → Reed 闪避 p50 0.25 s（R0）/ 0.23 s（你）；冲刺斩开始 → Reed 闪避 p50 0.35 s（你，n 7）、Reed 举盾 0.22 s（n 9）、Clapper 0.083 s（n 4）。
- **从状态切换到真正开始移动**（起手）：Reed 0.133 s、Bellbearer 0.083 s、Minister 0.1 s、Clapper 0（直接 15 u/s）、Choristor 0（一跳 0.15 s）、Reed 举盾 0.083 s、Clawmaiden 0.183 s 后消失。退开的距离（0.6 s 内，背离你那一侧为正）p50：Reed 4.9 u、Bellbearer 5.0、Minister 6.4、Clapper 5.4、Choristor 后跳 1.9 / 前跳 −2.0。
- **冲刺斩的命中时间**（你的录像，前方目标被打中的 230 次）：冲刺斩动画开始后 p5 0.117 s、p50 0.133 s、p95 0.233 s（Clapper p50 0.117 s）。

### 2.4 "往前闪"的来历【录】

0.6 s 内位移朝主角那一侧（< −0.5 u）的比例：Reed 闪避 9.7 %（R0），其中进状态时主角在冲刺的 35 %（R0）/ 40 %（你的录像，n 少）；Minister 闪避 3.4 %，冲刺后 18–23 %；Bellbearer 2.8 %；Clapper 0.04 %；Choristor 后跳 2.2 %（冲刺后 11 %）；Reed 举盾 60–72 %（它本来就飞向离你 3 u）；Choristor 前跳 86 %（它本来就往前）。所以你看到的"往前闪"有三种来源：Choristor 的前跳（距离 > 6–10 u 时）、Reed 举盾的起手、以及你冲过它身后时它按旧朝向"往后"退（退向你）。

### 2.5 你的冲刺斩（329 次：`Dash Upper Antic` 254、`Wanderer Dash Attack` 72、其他 3）【录】

前方 0–8 u 最近的敌人，冲刺斩开始前 0.1 s 到后 0.6 s 内有没有反应动作、有没有被打中（任何来源）：

| 目标 | 次数 | 打中 | 反应动作 | 反应时打中 / 先后 |
|---|---|---|---|---|
| Choristor | 137 | 116 | 62（后跳 58、前跳 4） | 51 / 62；后跳：先跳 27、先打中 20、没打中 11 |
| Reed | 86 | 58 | 23（举盾 17、闪避 6） | 10 / 23（无反应 48 / 63）；举盾：没打中 11（撞盾或没够着）、先打中 4、先举盾 2；闪避：先打中 3、没打中 2、先闪 1 |
| Clapper | 36 | 33 | 9（`Evade Scuttle`） | 9 / 9：先打中 4、先闪 5 |
| Envoy / Clawmaiden / Bellbearer / Minister / Tiny | 12 / 10 / 6 / 3 / 3 | 9 / 8 / 3 / 3 / 0 | 0 / 0 / 1 / 2 / 0 | — |

Choristor 的跳是它一直在做的走位（每次 `Move Start` 1–3 跳），冲刺斩只是把距离缩短，所以多半往后跳（方向按 §2.2 的公式）。

---

## 3. 对 bot 的含义

### 3.1 安全（S）【推，依据 §1.3 和 forum.md §12.2】

- **都在支撑里。** 闪避 / 跳步 / 瞬移 / 举盾都是行为表里已有的家族或决策后继，停留区间按录像记录（下限等于 FSM 门槛），R0 的支撑召回在 35 场新数据上已认证 100 %（forum.md §12.2），这些状态都在那批数据里。闪身本身没有攻击碰撞体，只有身体（Clapper 2 格，其余 1 格）；它们背离朝向移动，但约 10 % 的 Reed 闪避朝你那一侧——模板按敌人自己的朝向（flipX）记录，开始时朝向可见，所以也在支撑里。
- **要留意的两处**：(1) Clapper 闪到背后 6 u 内有墙时接 `Escape Jump`（跳砸 / 跳施法，2 格、瞄你前 5 u）：这条链在表里（`Escape Jump` 是决策状态），口袋规则（forum.md §10.4）照旧。(2) Reed 举盾后**被打中**的反击（2 格连段，可拼刀）：这是打中触发的，支撑里有（RE_DEFEND 的模板含 `Parry Slash`），但规划器要知道"向举盾中的 Reed 出刀 = 触发反击"，见 3.2。
- 没有发现"动作触发、支撑里没有"的漏洞。

### 3.2 预测与规划：反应分支（只进 J / P，不进 S）

闪不闪是候选计划自己决定的，和命中效果分支同类。建议：

1. **静态数据** `reactive_triggers.json`（从本文 §1.2 的表生成，`ranges.py` + FSM 解码）：每类每个机制的源状态、触发形状（相对 transform，盒 / 圆并集，四周 +0.05 u）、门槛（Reed 上膛：`Defend Start` / `Stab Antic` 开、`Evade Antic` 关；`Just Did Defend`；Bellbearer 冷却：`Evade` 开、`Throw Antic` 关，`In Range` ≥ 0.5 s，背后 3 u 无墙；Clapper `Idle` ≥ 0.25 s；Minister 只在 `Evade?`；Choristor `Hop Check` 的公式）、隐藏硬币（Clapper `Will Evade`、Reed `Will Defend`：0.5，**同一轮里你已在盒内且门槛开着而它没反应，就说明硬币是反面，本轮 p = 0**）、延迟（1 帧）、起手和运动模板（就是行为表里该家族的按状态模板）。
2. **EnemyTracker 维护门槛状态**：都能从看得见的事件推出（上一次举盾 / 突刺 / 扔铃 / 闪避、进当前状态的时刻），视觉路径同样可用（M3 的可观测阶段表要包括这些状态）。
3. **反应分支**：对阶段 2 的每一行（已做包络的候选），沿它的主角物理盒轨迹找每个"在源状态、门槛开"的敌人第一次进盒的步 t_e（敌人位置用它当前状态的外推）；以 p 在 t_e + 1 帧把该敌人切到闪身模板（起手 + 背离朝向的位移），1 − p 保持原预测。J 里对该敌人的命中按两支加权：`hits_k = (1 − p)·hits_nominal + p·hits_dodge`。上限像命中效果一样（每 tick 前 K 行、每行最多 2 个敌人）。属性测试：S、Hz、U 与关掉反应分支时逐位相同。
4. **J 会变的地方**：
   - **冲刺斩的期望伤害**：Reed / Bellbearer 门槛开着时，冲刺途中（冲刺斩前）就进盒 → 0.133 / 0.083 s 后它以 30 / 32 u/s 离开，冲刺斩落空；进盒的那一步就是冲刺斩开始（刀 0.12–0.13 s 到）→ 刀先到。冲刺斩打 Reed：带反应时 43 %、不带时 76 %（§2.5）。
   - **打空窗（诱闪再打）**：Reed 闪过一次就"没子弹"，直到它下一次举盾或突刺；Bellbearer 闪过一次要等它下一次扔铃。这段时间里冲过去不会被闪掉——这是冲刺斩 / 飞针打这两类的最好时机。诱的方法就是让身体进一下盒（Reed 的盒在它正下方 ±1.5 u 一整条、同高到上方 ±3.8 u；Bellbearer ±3.3 u）再退出。Clapper：在 Slam Range 里待到它 `Idle` 0.25 s，硬币正面就闪；闪完 `After Scuttle` 你还在范围里它**只会锤或施法**（不会再闪），所以追上去是危险的，不是空窗。Minister 的闪避只在它出完招之后、你在 4.95 u 内时（50 %），闪完 6.5 u 外回 `Chase`，没有空窗价值。
   - **别撞盾**：Reed `Alert` 里、`Just Did Defend` 为假时，你进 7.65 u 就有 50 % 它举盾（EVADE 优先：同时在 Evade Range 里就是闪）；对举盾的 Reed 出刀 → `BLOCKED HIT` → 2 格连段反击。打分里把"向可能举盾的 Reed 冲刺斩"的期望伤害和反击风险（P）算进去。
   - **拼刀时机**：闪身状态都没有攻击碰撞体，没有可拼的东西；Reed 举盾后的反击可拼（parry 5，forum.md §12.4），R8 的拼刀分支照旧。
5. **打中触发的反应**（§0 第 4 点）属于命中效果分支：候选的刀在 t 打中 → 该敌人按 FSM 的被打中出边切换（Clapper `Idle` → `Dmg Attack` → 你在 Slam Range 就 1/3 锤 / 闪 / 施法；Reed `Alert` → `Stab Pos`；Minister / Maestro 下一招提前；Envoy 冲锋）。支撑本来就含这些后继；要改的是打分：例如"打 `Idle` 的 Clapper 一刀后，接下来 0.1 s 内 1/3 概率出锤"该进 P。

**归属**：反应分支和门槛跟踪放 **R5**（它的第一项"决策的感知时刻"就是同一份 FSM 静态提取：每个决策读主角位置的动作在哪个状态、是每帧还是只在进入时——这里的结论：Reed `Alert`、Bellbearer `In Range`、Clapper `Idle` 每帧读；Choristor `Hop Antic` 只在进入那一帧读；`Hop Check`、Minister `Evade?`、Clapper `Close Range` 是瞬时决策），只改 J / P；"诱闪再打""打空窗"作为 **R6** BAIT / FOCUS 的目标；冲刺斩原语本身（`M_DASH_STAB`）在 **R7**；举盾反击的拼刀在 **R8**。R3 的命中效果分支扩到敌人一侧（打中触发的出边）。

### 3.3 行为表的协变量（"主角当前动作"）【录】

在每个决策状态的出边上，基线 = P(下一状态 | |dx| 档 0/3/6/10 u、高度档、左右)，候选 = 再加主角当前动作组（冲刺斩 / 飞针 / 冲刺 / 出刀 / 无），Dirichlet 平滑，按场 2 折留出对数损失（`covariate_test`）：

| 数据 | 决策状态数 / 决策数 | 加权平均增益（nats / 决策） | 增益 > 0 且区间不含 0 的 |
|---|---|---|---|
| R0 | 29 / 263,543 | −0.0003 | Clapper `Idle` +0.012 [0.010, 0.015] |
| R1 | 27 / 61,071 | −0.004 | Clapper `Idle` +0.064 [0.049, 0.079]、Tiny `Ready` +0.004 |
| 你 | 24 / 16,504 | −0.019 | Minister `Chase` +0.053 [0.017, 0.087]、Tiny `Ready` +0.059、Choristor `Unalert Tick` +0.016 |

变好的都是有"被打中"出边的状态（Clapper `Idle → Dmg Attack`、Minister `Chase → Range Check`）：出刀预测"马上会被打中"。**建议不把主角动作加进行为表**；要加的是 (1) "主角身体在某个触发盒里"（精确几何，替代这些状态的距离分档：Minister `Evade?` 在盒内 0.485、盒外 0；Choristor `Hop Check` 用公式），(2) "刚被打中"（区分被打中出边；规划器里由命中分支提供）。这两个都是视觉可得的。

### 3.4 实机探针（写好、没跑）

`C:\ssbot\sandbox\reactive_scripts\probe_dash_stab.py`：从波次起点存档（默认 `fo_r1_w8`：两只 Reed + Bellbearer）对指定类型的敌人做冲刺斩（按住冲刺、冲刺后 `--attack-delay` 秒按攻击，出 Reaper 的 Dash Upper），每次记录 1.2 s 的主角与目标逐帧状态和事件，离线算"进盒帧、闪身帧、命中帧"。目的：给 3.2 的冲刺斩期望伤害一个按"进盒时刻 − 冲刺斩开始"分档的命中率（你的 329 次里 Reed 只有 86 次、带反应 23 次），并核对 Reed 上膛 / 未上膛时的差别。需要一个空闲实例，读档、会抢焦点。

---

## 4. 没弄清的

1. 冲刺斩打闪身的精确时间窗（3.4 的探针）；bot 自己的数据几乎没有冲刺斩（R1 的 DASH_IN 没出冲刺斩，§0 第 7 点）。
2. Reed 已上膛、身体在盒内但这一轮没闪的 10–25 %（R0 / R1）：被打中抢先之外的部分没有逐个查【推：同一帧的 `Choice` 计时或视线检查】。
3. Bellbearer 48 次（R0 1.1 %）在主角不在盒里、另一只同名 Bellbearer 同时在 `Evade Antic` 时"闪"：导出把同名实体串了，还是真有联动，未查清（实机看一次两只同时在场时的 `fsm` 事件即可）。
4. Clapper 冲刺组 `Idle` 闪避偏低（R0 0.32，n 132）的原因【推，见 2.2】。
5. Clawmaiden 的 `Tele Escape Range`（2.66 u）在 3 份数据里一次都没触发：她瞬移落点离主角有下限，主角很少正好站进去。

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
..\scripts\uv.cmd run python C:/ssbot/sandbox/reactive_scripts/reactive.py --out C:/ssbot/sandbox/reactive_scripts/reactive_full3.json
```

R1 抽取用的运行：`20261004_105441_Forum_A_w3_mix_data2`、`110245_*`（2 个）、`111158_*`（2 个）、`130403_*`（2 个）、`131323_*`（2 个）、`143803_*`（2 个）、`153511_Forum_A_w7_mix_data2`、`144623_Forum_A_w7_mix_data_idle_oracle`（可读的 218 局；2× 和当时可能还在写的 `1546xx`、`155649` 没用）。全部约 15 min（R0 7 min、R1 4 min、人 3 min）。
