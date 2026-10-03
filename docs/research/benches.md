# 工作台调研：付费、有条件、假椅，以及路线上紧急退出的回撤（2026-10-03）

起因：你问"路线包括买椅子吗"。DESIGN §3.6.4 已加了规则（付费 / 有条件工作台按"附近 A 类遭遇的预期退出次数 × 每次少走的回撤 − 念珠和绕路"排序），但缺数据。本文从游戏数据列出**全部**工作台，找出要付钱、要条件、会坏或是假的那些，说明坐下是否设置存档退出后的重生点、购买时能否暂停；然后按 §3.6.4 的路线表，给每个危险遭遇找最近的工作台、估回撤时间，并排序。

**标签：** 【包】离线 UnityPy 读训练副本 1.0.30000 的场景包（`scenes_scenes_scenes/*.bundle`）和 `dataassets`；【码】反编译 1.0.30000 C#（`C:\ssbot\decomp\1.0.30000\Assembly-CSharp`，文件:行）；【录】我们自己的录像和由录像生成的 `knowledge/1.0.30000/quit_map.json`；【攻】社区资料（社区路线逻辑图 `room_graph_data.json`、wiki、指南），没有用游戏数据核对；【估】下文 §3 的门距模型估计；【推】推断；【未核实】待实测。

**脚本与原始输出：** `C:\ssbot\sandbox\bench_scripts\`（全部离线，idle 优先级，没有连接任何游戏实例）。`bench_scan.py` → `bench_scan.jsonl`（全部 590 个场景包里带 `RestBench` 组件或 `Bench Control` FSM 的对象，含祖先链上的条件组件和 FSM 变量）；`bench_extra.py` → `bench_extra.txt`（钟椅 `BellBench` 字段、收费机 FSM 的 `Cost Reference`）；`costs.py` → `costs.txt`（`dataassets/costs.bundle` 全部价格资产）；`fsm_dump3.py`（能解出 byteData 参数的 FSM 导出器）及其输出 `fsm3_*.txt`、`fsm_*.txt`；`find_tpl.py`（FSM 模板）；`gates_all.py` → `gates_all.json`（所有场景的门坐标和 BattleScene）；`walk.py` / `nearest.py` → `nearest.txt`（§3 的回撤估计）；`gen_table.py` → `bench_table.md`（附录 A）；`refscan.py`、`scan_str.py`、`goname.py`、`fields.py`（查引用、字符串、对象名、组件字段）。核查后的修订另加：`fix_near.py`（按区域 / 名字列对象的世界坐标、激活链、组件、FSM 名）→ `fix_near_coral32_top.txt`、`fix_near_coral38.txt`、`fix_near_coral11.txt`、`fix_near_forge_battle.txt`；`fix_lift.py` → `fix_lift_coral38.txt`（升降梯各停靠点和呼叫板）；`fsm_dump3.py` 的新输出 `fix_fsm_cogdancers_sequence.txt`、`fix_fsm_coral32_crustwall.txt`、`fix_fsm_room_pinstress.txt`；`walk.py` 重算 → `fix_walks.txt`。方法沿用 Forum 路线调研（`research/forum_route.md`，分支 `worktree-wf_c0d56d51-4cb-5`）。

**修订（2026-10-03，事实核查之后）：**
1. **Lace 2 退出后不用重新演奏旋律**：第一次演奏结束时游戏置 `UnlockedMelodyLift` 并存档，之后从 `Cog_Dancers` 坐升降梯进 `Song_Tower_01`（§3.1、§3.2）。一次性解锁过场里有不能暂停、不能存档退出的窗口（§1.3）。
2. **`Bellway_08` 不再列为"买"**：基线改为路线上免费坐的 `Bonetown`，交战门的影响单独建模；默认不买，按 K1/M2/M5 的实测用 §4.2 的判据决定（§0.7、§4、§7）。
3. **Last Judge 的两张候选椅子已查**：`Bellshrine_Coral` 在 S17 从下方到不了（`Coral_38` 的升降梯只有上方呼叫板能解锁）；`Room_Pinstress` 要经过 Great Conchflies 的 boss 闸门（§3.2 补充）。
4. Fourth Chorus 和 Hunter's March 竞技场改用 boss / 闸门的实际坐标，回撤变长（§3.2）；`Room_Forge` 的 5 波竞技场写进 Lace 1 行（§3.2、§5）；每次退出的回撤只给一个区间（§0.8、§6）。
5. 核查提到的 decomp 行号偏差：用 `sed -n` 对 `C:\ssbot\decomp\1.0.30000\Assembly-CSharp\GameManager.cs`（CRLF，5,528 行）复核，本文原引的 1626（`skullKingDefeated` 入侵条件）、1734–1749（`BelltownHouseState`）、2167（`StartAct3` 改写重生点，2167–2169）都对得上，未改。

## 0. 结论摘要

1. **工作台总数**：场景包里有 100 个 `RestBench` 对象，去掉第三幕变体、假椅和不可用的，**80 个场景有可用工作台**（DESIGN §3.4.1 引的 Benchwarp 是 81 个，基本一致）【包】。分类（附录 A）：免费 50、付费 16、付费且有条件 1、有条件 22、假椅 5、不可用 3、第三幕变体 3。
2. **要付钱的工作台有三种**【包】：
   - **钟椅（`BellBench` + `bell_toll_machine`）**，付一次永久升起：Marrow `Bone_01c` 30、Deep Docks `Dock_01` 30、Far Fields `Bellway_03` 30 和 `Bone_East_15` 30、Blasted Steps `Bellway_08` 40 和 `Coral_02` 60、Shellwood `Shellwood_01b` 40 和 `Shellwood_08c` 40、Sinner's Road `Dust_10` 40（另需修好）、Mount Fay `Bellway_Peak` 60、Putrified Ducts `Bellway_Aqueduct` 60、Bilewater `Bellway_Shadow` 60。价格来自收费机 FSM 引用的 `CostReference` 资产（Bell Bench Toll Lowlands 30 / Midlands 40 / Upperlands 60，两处引用了 Bellway Toll Midlands 60），**不是** FSM 里的 `Cost` = 100 默认值。
   - **Underworks 收费椅（Understore Toll Bench）**：`Under_01b` 2 张、`Under_08` 3 张，**每次坐都要付 15**，起身后翻回收费状态。
   - **收费门后的工作台**：Pilgrim's Rest（`Bone_East_10_Room`）的门 30（Pilgrims Rest Door），DESIGN §3.6.5 的"入场费"就是它。
3. **坐下就设置存档退出后的重生点**【包】【码】：`Bench Control` FSM 的 `Set Spawn Location` 在 `Set Respawn` 为真、`z_FakeBench` 为假时写 `respawnScene`、`respawnMarkerName`、`respawnType = 1`，随后 `Save Game` 状态调用 `TimePasses` 并存档。Continue 时 `GameManager.GetRespawnInfo` 只看 `respawnScene`/`respawnMarkerName`（`tempRespawn*` 不存档）。所有真工作台的 `Set Respawn` 都是 1；**5 张假椅不设重生点**。付费钟椅、收费椅、收费门后的工作台坐下后都和普通工作台一样设置重生点；收费椅在你从它上面醒来时直接处于坐下状态，不用再付【推：其 FSM 在 `Init`/`Inert` 收到 `BENCHREST START` 直接进 `Start Sitting`，事件来源未逐条核实】。
4. **购买时不能暂停**【码】【包】【录】：收费机是 NPC 交互，交互期间 `InteractManager.BlockingInteractable` 非空，`GameManager.PauseGameToggle` 直接拒绝（`GameManager.cs:4992`，只有 `atBench` 时例外）。从按"是"到付款动画结束约 5 s 不能暂停（我们录像里 `Bone_01c` 有一段 4.87 s 的 BLOCKING_INTERACT，暂停概率 0）。确认框期间受击会取消购买（模板 `toll_dish_sub`：`HERO DAMAGED` → `Cancel`）。之后钟椅升起约 5 s，可以暂停。**坐在工作台上可以暂停**（`atBench` 为真时不受 BlockingInteractable 限制），开地图时 `disablePause` = 1。
5. **路线相关的有条件工作台**【包】【码】：Hunter's March 唯一的工作台 `Ant_17` 是**陷阱椅**：拉杆 `ant_lever_persistent` 置 `antBenchTrapDefused` 之前坐下会触发镰刀陷阱（伤害 2），之后才是真工作台；五个钟塔（Marrow、Deep Docks、Greymoor、Shellwood、Songclave）的工作台**敲钟后才出现**；Songclave 的工作台要 `enclaveLevel` ≥ 1；跳蚤商队的工作台跟着 `CaravanTroupeLocation` 走（Greymoor_08 只在 = Greymoor 时有）；Last Judge 竞技场的商队工作台要打完 Last Judge 且商队到了那里；Bellhome 要完成两个 Bellhart 许愿；Bone Bottom 的工作台只有在 Skull Tyrant 入侵时会坏，入侵要先打败 Skull Tyrant，本路线不会发生。
6. **最大的收益是免费的**【估】：几乎每个 A 类战斗附近一两个房间内都有免费工作台，路线本来就经过，只要**战前坐下**：Moss Mother（`Tut_03`，同房间）、Bell Beast（`Bone_04`，隔 1 道门）、Lace 1（`Room_Forge`，隔 1 道门；房间里有 5 波竞技场，见 §3.2）、Fourth Chorus（`Bone_East_Umbrella`，隔 2 道门，门的可用性未实测）、Widow（`Belltown`，2 道门）、Trobbio（`Bellway_City`，2 道门）、Forum（`Hang_06b`）、Lace 2（`Cog_Bench` → `Cog_Dancers` 的升降梯，第一次演奏 Threefold Melody 解锁后可重复乘坐）、GMS（`Tube_Hub`，1 道门）。按门距模型，除 Last Judge 外这些回撤是 **约 10–85 s**（另加 boss 进场过场，未测），远低于 DESIGN §3.6.6 每次退出 380 s 的先验。
7. **默认不买任何工作台；唯一接近盈亏平衡的是 Blasted Steps 的 `Bellway_08` 钟椅（40 念珠），给 Last Judge 用**【估】【推】。它在 `Coral_03`（Blasted Steps 大竖井）顶端旁边；路线上免费可坐的是竖井下方的 `Bonetown`（S17 路过），`Bellway_08` 比它每次回撤少约 67–134 s（中值约 100 s）并跳过整段竖井。成本约 12 s 绕路 + 14 s 购买 + 40 念珠。只算紧急退出（Last Judge q = 0.34 次 / 局，先验）时约 **−32 s / 局**；它的另一项价值是交战门：从 `Bonetown` 出发、爬完竖井到 Last Judge 门口时不满血的概率 p 越大越值。按 §4.2 的判据，**p ≥ 约 0.07、或 Last Judge 的 q ≥ 0.66、或 S17 时念珠有余（成本降到约 26 s，q ≥ 0.26 即可）时买**，否则不买；这三个量等 K1/M2（q）、M5 oracle（p、念珠收入）实测后定。附近的免费替代 `Bellshrine_Coral` 在 S17 到不了，`Room_Pinstress` 在 Great Conchflies 的闸门后面（§3.2）。其余付费工作台都不如附近的免费工作台，或附近没有我们要打的 A 类战斗，**不买**；Far Fields `Bellway_03`（30）只在 Pinstress 小屋的工作台实测不可用时作为 Fourth Chorus 的后备（同样按 §4.2 判据）。
8. **对时间预算**【估】【推】：如果路线在每个 A 类战斗前坐最近的工作台，按门距模型每次紧急退出的单程回撤约 **10–85 s**；Last Judge 是例外，从 `Bonetown` 约 110–220 s（买 `Bellway_08` 后约 45–85 s）。另加 Continue 读档（P7 待测）、boss 进场过场和重新清场（DESIGN §3.7.5 第 6 步），模型还低估竖井和平台。DESIGN 的 380 s × 4.5 = 1,700 s 这一行可能偏高，但这只是**待 M5 oracle 实测检验的假设**，不据此改预算（§6）。

## 1. 机制（所有工作台通用）

### 1.1 坐下时设置什么【包】【码】

- 每张真工作台是一个带 `RestBench`（碰撞触发 `HeroController.NearBench`）、`RespawnMarker`、`RestBenchHelper` 和 PlayMakerFSM `Bench Control` 的对象（`RestBench.cs`、`RestBenchHelper.cs`；`bench_scan.jsonl`）。`Bench Control` 的每实例变量里与本题有关的是：`Set Respawn`（bool）、`z_FakeBench`（bool）、`Check For PD Bool`（string）、`Spawn Name` / `Scene Name`（运行时填）。
- 坐下流程（`fsm3_bench_caravan.txt`，所有实例同一模板）：`At Bench`（置 `atBench`、`disableInventory`）→ `Set Spawn Location`：`Set Respawn` 为假或 `z_FakeBench` 为真则跳过；否则 `respawnMarkerName = Spawn Name`、`respawnScene = Scene Name`、`respawnType = 1` → 设置地图区域 → … → `Save Game`：`GameManager.TimePasses()` + `SaveGame`。旧的 `Rest Burst` 里同样的设置动作已被禁用（`[DISABLED]`），所以只有 `Set Spawn Location` 生效。
- `Check For PD Bool` 非空时，`Check Inactive` / `Is Active?` 状态测这个 PlayerData 布尔值，为假就进 `Inactive`，不能坐。全游戏只有 `Ant_17` 用了它（`antBenchTrapDefused`）。
- 100 个对象里，除两张陷阱假椅（`Bone_East_18b`、`Bone_East_26`，`Set Respawn` = 0）外 `Set Respawn` 都是 1；`z_FakeBench` = 1 的共 5 个（附录 A 的"假椅"）。
- 其他会改重生点的东西（不属于工作台，但会覆盖它）：`SetDeathRespawnMarker` 动作（例如 Reaper 神龛，forum_route §2）、`RespawnTrigger`、`GameManager.SetDeathRespawnSimple`、Act 3 开场（`GameManager.cs:2167`）【码】。

### 1.2 存档退出后 Continue 从哪里出来【码】

- `GameManager.RunContinueGame` → `ReadyForRespawn(isFirstLevelForPlayer: true)` → `GetRespawnInfo`（`GameManager.cs:1030-1073`）：`tempRespawnScene` 非空时用它，否则用 `respawnScene` / `respawnMarkerName`。`tempRespawn*` 只由非致命死亡设置，且是不存档字段（`PlayerData.ResetNonSerializableFields`，`PlayerData.cs:3937`），所以**存档退出后一定回到最后一次坐下的工作台**（或上面列出的其他重生点设置者）。
- 重生点要在 `SceneTeleportMap` 的 `RespawnPoints` 里，否则回到 `Tut_01` 的 "Death Respawn Marker Init" 并清掉临时重生点（`GameManager.cs:1053-1072`，兜底在 1070 行）。工作台都是正常注册的重生点，这条只是兜底【推】。
- 出生时如果工作台对象在场景里没有激活，就用它的子对象 `Alt Respawn Point`（`HeroController.cs:7197-7203`）。例子：`Greymoor_08` 主场景里有一个未激活的 `RestBench`（只有 `RespawnMarker`），商队附加场景不加载时就靠它出生【包】。
- `respawnType == 1` 且找到 `Bench Control` 时，以坐姿出生并给工作台 FSM 发 `RESPAWN`（`HeroController.cs:7216-7224`）。

### 1.3 暂停【码】【包】【录】

- 暂停的门：`InputHandler` 要求 `acceptingInput`、`PauseAllowed`、`!disablePause` 且状态为 PLAYING（`InputHandler.cs:348, 443`）；`GameManager.PauseGameToggle` 另外拒绝 `TimeSlowed`、`GenericMessageCanvas`，以及 **`InteractManager.BlockingInteractable` 非空且不在工作台上**的情况（`GameManager.cs:4987-4992`）。
- **坐在工作台上**：`atBench` 为真，可以暂停（开地图时 `Open Map` 置 `disablePause` = 1，关地图恢复）。走向工作台到 `At Bench` 之间的约半秒仍在交互中，不能暂停【推】。
- **购买**：收费机（`bell_toll_machine`、`Understore Toll Bench`、Pilgrim's Rest 的 `toll door interactible`）都是 `PlayMakerNPC` 交互，付款子流程是共享模板 `toll_dish_sub`（`fsmtemplates_assets_shared.bundle`）：`Confirm`（`GetCostFromReference` + `DialogueYesNoV3`，`HERO DAMAGED` → `Cancel`）→ `Start Sequence` → `Wait For Currency Counter`（`TakeCurrency`）→ `Taking Currency`（逐个扣念珠的动画）→ 收尾。整段 BlockingInteractable 非空，**不能暂停**。我们的录像：`quit_map.json` 的 `Bone_01c` 有一段 4.87 s 的 BLOCKING_INTERACT，`p_pause` = 0【录】（推测就是付钱；全局 `interact` 类 269 s 中 `p_pause` = 0.064）。模板里没有 `disablePause` 动作【包】。
- **钟椅升起**：付完后 `Retract Animation` 结束对话（交还控制），再由 `BellBench.Behaviour` 协程升起：`moveUpPause` 0.3 s + 架子从锁定位置升约 10 u（`moveUpSpeed` 4 → 约 2.5 s）+ `benchRaiseDelay` 1.3 s + 假椅出现动画 + 真椅淡入 0.5 s，约 5–6 s【包 `Bone_01c` 的 BellBench 字段】【码 `BellBench.cs`】。这段可以暂停，但工作台还不能坐。
- **整次购买的耗时**【推】：确认 + 付款约 5 s（不能暂停）+ 升起约 5–6 s + 坐下约 2–3 s ≈ **13–15 s**。
- 监督器：购买的 5 s 要像 Cogfly 合成一样登记成确定性禁暂停窗口，只在无威胁、GREEN、满血时确认（与 forum_route §4 的做法一致）。
- **另一个与工作台回撤有关的窗口：`Cog_Dancers` 的一次性解锁（S26 第一次演奏 Threefold Melody）**【包 `cog_dancers` 的 `Boss Scene` FSM `Sequence`，`fix_fsm_cogdancers_sequence.txt`】：`Needolin Prompted Full` 置 `disablePause` = 1，直到雕像唱完、对话结束后的 `Return Control` 才恢复 0；接着 `Break Lock Pt1` 置 `disableSaveQuit` = 1，`Break Lock Pt2` 置 `UnlockedMelodyLift` = 1、`QueueSaveGameV2`（存档）并把 `disableSaveQuit` 恢复 0。所以这段过场里先不能暂停、再不能存档退出。Dancers 已打完、房间里没有敌人，风险低，但 quit map 和 §3.7.5 要登记这两个窗口（时长未测）。

### 1.4 价格表（`dataassets/costs.bundle`，`costs.txt`）【包】

| 价格资产 | 念珠 | 用在 |
|---|---|---|
| Bell Bench Toll Lowlands | 30 | `Bone_01c`、`Dock_01`、`Bellway_03`、`Bone_East_15` 的钟椅 |
| Bell Bench Toll Midlands | 40 | `Bellway_08`、`Shellwood_01b`、`Shellwood_08c`、`Dust_10` 的钟椅 |
| Bell Bench Toll Upperlands | 60 | `Bellway_Aqueduct`、`Bellway_Shadow` 的钟椅 |
| Bellway Toll Midlands | 60 | `Coral_02`、`Bellway_Peak` 的钟椅（也是 Bellway 站的价格） |
| Understore Toll Bench Default | 15 | Underworks 收费椅（每次） |
| Pilgrims Rest Door | 30 | Pilgrim's Rest 的门 |
| （参考）Bellway Toll Lowlands / Midlands / Upperlands | 40 / 60 / 80 | Bellway 站 |
| （参考）City Tube Toll Default | 80 | Ventrica 站 |

收费机 FSM 的 int 变量 `Cost` 一律是 100，但付款模板只读 `Cost Reference`（`toll_dish_sub` 的 `Confirm` 状态 `GetCostFromReference`），所以 100 不是实际价格。

### 1.5 条件类型一览

| 类型 | 机制 | 例子 |
|---|---|---|
| 敲钟后出现 | 钟塔场景的 `Whole Scene/Bell Bench` 由 Bellshrine Sequence 的 `Bench Appear Sequence` 升起 | `Bellshrine`、`Bellshrine_02/03/05`、`Bellshrine_Enclave`；`Belltown_Shrine` 在 Widow 的 Boss Scene 下 |
| 付钱升起 | `BellBench` + `bell_toll_machine`（`Unlock Behaviour`）：付款后 `PersistentBoolItem.SaveState`，以后进场景直接 `Opened()`；同时置 `hasActivatedBellBench`，`Bellway_08` 另置 `activatedStepsUpperBellbench` | §1.4 |
| 坏椅 | `BellBench.fixedPDBool` 非空时，该 PlayerData 布尔为假则椅子处于坏的状态（`BellBench.cs:176`） | `Dust_10`：`FixedDustBellBench` |
| PlayerData 布尔 | `Bench Control.Check For PD Bool` | `Ant_17`：`antBenchTrapDefused` |
| 商队位置 | `CaravanTroupeLocation`（Bone 0 / Greymoor 1 / CoralJudge 2 / Aqueduct 3），由商队 FSM `Quest End Sequence` 的 `Set Location` 改写 | `Bone_10`（0）、`Greymoor_08_caravan`（1）、`Coral_Judge_Arena`（2 且 `defeatedLastJudge`）、`Aqueduct_05_*`（3） |
| Songclave 等级 | `enclaveLevel` ≥ 1 | `Song_Enclave` 的 Level 1 工作台（forum_route §1.1） |
| 先破坏 | Breakable + PersistentBoolItem | `Organ_01`（蛛网） |
| 许愿 | quest 完成 + TimePasses | Bellhome（`Belltown_Room_Spare`） |
| 收费门 | 门是收费机 | Pilgrim's Rest |
| 第三幕 / 钢铁之魂变体 | `blackThreadWorld`、`permadeathMode` 的 TestGameObjectActivator | `Song_Enclave`、`Bone_10`、`Bone_12` 的 Black Thread 版；`Dust_11` 的钢铁之魂版 |
| 假椅 | `z_FakeBench` = 1，不设重生点 | `Bone_East_18b`、`Bone_East_26`（陷阱椅）、`Shadow_15`（会塌）、`Room_Diving_Bell`、`Room_Diving_Bell_Abyss_Fixed`（旅行座位） |

## 2. 付费和有条件的工作台（详表）

坐标是场景世界坐标【包】。"设重生点"一栏：是 = `Set Respawn` 1 且非假椅，Continue 后从这里出来（§1.2）。暂停一栏指购买或解锁动作期间。

| 场景（区域 / 房间） | 坐标 | 价格 / 条件 | 怎么满足 | 购买 / 解锁时暂停 | 设重生点 |
|---|---|---|---|---|---|
| `Bone_01c`（Marrow / The Marrow Bell Bench） | (168.3, 8.0) | 30，一次 | 付钱【包】 | 约 5 s 不能【码】【录】 | 是 |
| `Dock_01`（Deep Docks / Bench Shaft） | (19.2, 65.0) | 30，一次 | 付钱 | 同上 | 是 |
| `Bellway_03`（Far Fields / Far Fields Bellway） | (49.4, 10.0) | 30，一次 | 付钱（同房间还有 Bellway 站收费机 40，是另一台） | 同上 | 是 |
| `Bone_East_15`（Far Fields / Deep Docks Loopback） | (35.4, 54.0) | 30，一次 | 付钱 | 同上 | 是 |
| `Bellway_08`（Blasted Steps / Blasted Steps Bellway） | (120.6, 14.0) | 40，一次 | 付钱；同时置 `activatedStepsUpperBellbench` | 同上 | 是 |
| `Coral_02`（Blasted Steps / Toll Bench Bottom） | (195.9, 5.1) | 60，一次 | 付钱 | 同上 | 是 |
| `Shellwood_01b`（Shellwood / Sister Splinter Bench） | (23.3, 37.1) | 40，一次 | 付钱；同房间有 3 波 BattleScene | 同上 | 是 |
| `Shellwood_08c`（Shellwood / Lower Toll bench） | (14.9, 5.1) | 40，一次 | 付钱 | 同上 | 是 |
| `Dust_10`（Sinner's Road Bench） | (122.2, 45.0) | 40，一次 + `FixedDustBellBench` | 付钱，另需修好（`Mapper Sit NPC` 的对话 FSM 读这个旗标，修理方式未展开） | 同上 | 是 |
| `Bellway_Peak`、`Bellway_Aqueduct`、`Bellway_Shadow` | 见附录 A | 60，一次 | 付钱 | 同上 | 是 |
| `Under_01b` ×2、`Under_08` ×3（Underworks 收费椅） | 见附录 A | **每次 15** | 每次坐前付；在它上面醒来不用付【推】 | 同上 | 是 |
| `Bone_East_10_Room`（Pilgrim's Rest 店内） | (53.4, 12.5) | 门 30 | `Bone_East_10` 的 `toll door interactible` 付 30，或 Rhino 撞开门（`PilgrimsRestDoorBroken`） | 付门时不能 | 是 |
| `Ant_17`（Hunter's March Trapped Bench） | (29.0, 5.9) | `antBenchTrapDefused` | 打房间左侧拉杆 `ant_lever_persistent`（11.0, 8.7）；之前坐下会触发 `Hunter Sickle Trap`（伤害 2，flags 0）且 `Bench Control` 处于 Inactive，不设重生点 | 打拉杆不涉及交互 | 拉杆后是 |
| `Bellshrine`、`Bellshrine_02`、`Bellshrine_03`、`Bellshrine_05`（四个钟塔） | (20.5, 5.2) | 敲钟 | 敲该钟后升起（Bellshrine_Enclave 已逐状态核实，其余同一预制体【推】） | — | 是 |
| `Bellshrine_Enclave`（Songclave 钟塔） | (28.5, 5.2) | 敲 Songclave 钟 | forum_route §1.1 | — | 是 |
| `Song_Enclave` Level 1（Songclave） | (38.8, 6.7) | `enclaveLevel` ≥ 1 | 敲钟 → Caretaker 过场 → 在 Songclave 和钟塔以外 TimePasses（forum_route §1.1） | — | 是 |
| `Belltown_Shrine`（Widow 竞技场） | (52.8, 9.9) | 打完 Widow | Boss Scene 下的 Bell Bench【推】 | — | 是 |
| `Greymoor_08` 商队 | (43.9, 4.2) | `CaravanTroupeLocation` = Greymoor | `Bone_10` 商队的 `Quest End Sequence` 收到 `QUEST END TRAVEL/NOTRAVEL` 后改写位置；触发它的 quest【未核实】 | — | 是（商队走后从主场景的占位标记出生） |
| `Bone_10` 商队（Marrow） | (24.6, 15.4) | `CaravanTroupeLocation` = Bone | 初始状态 | — | 是 |
| `Coral_Judge_Arena` 商队 | (23.2, 23.7) | `CaravanTroupeLocation` = CoralJudge 且 `defeatedLastJudge` | 商队第二次搬家 + 打完 Last Judge | — | 是 |
| `Belltown_Room_Spare`（Bellhome） | (27.8, 6.8) | `BelltownHouseState` = Full | quest "Belltown House Start" → Half、"Belltown House Mid" → Full，都在 Bellhart 以外的 TimePasses 推进（`GameManager.cs:1734-1749`）；门 `Hornet House States/door5` 只在 Full 时激活 | — | 是 |
| `Organ_01`（Bilewater Exhaust Organ） | (52.3, 30.4) | 先打掉蛛网 | `Organ Webbed Bench` 是 Breakable | — | 是 |
| `Bonetown`（Bone Bottom） | (238.8, 6.9) | 只在 Skull Tyrant 入侵时坏 | 入侵前提 `skullKingDefeated`（`GameManager.cs:1626`），本路线不打 Skull Tyrant → 一直可用 | — | 是 |
| `Song_01b`、`Dust_Maze_09_Entrance` | 见附录 A | **不可用** | RestBench 在包里未激活，场景里找不到激活它的对象 | — | — |
| 5 张假椅 | 见 §1.5 | **不是工作台** | `z_FakeBench` = 1 | — | **否** |

## 3. 路线上的危险遭遇与最近的工作台

### 3.1 方法【估】

- 图：`gates_all.json` 里每个场景的 `TransitionPoint` 世界坐标和 `targetScene` / `entryPoint`【包】。房间内用门到门的直线距离，过门代价 0.5 s。用 Dijkstra 从遭遇点反向求所有工作台的最短距离（`nearest.py`）。
- 节奏：与 forum_route §6 相同，用你的录像校准：有敌人或平台的房间约 4 u/s、通畅走廊约 8 u/s【录】。下表的"回撤"是 `距离/8 + 0.5 × 门数` 到 `距离/4 + 0.5 × 门数` 的区间，**只是单程走回去的时间**，不含 Continue 读档醒来（P7）、boss 进场过场、重新打竞技场。
- 局限：不看能力要求、单向门和房间内的真实路线（攀爬按直线算），所以竖井多的路线被低估；工作台本身能不能在那个阶段到达，下表单独标注。遭遇位置：boss 用场景包里 boss 对象的坐标，竞技场用 BattleScene 所在房间的入口门。修订：Fourth Chorus 改用附加场景 `bone_east_08_boss_golem` 里 `Boss Scene/song_golem` 的坐标 (80.8, 7.5)（初稿只算到房间门口）；Hunter's March 竞技场 `Ant_04_mid` 改用普通世界 Battle Scene 两道闸门 `Battle Gate Ant` (185.3, 14.6) / (213.2, 14.6) 的中点 (199, 15)（BattleScene 根对象的坐标 (5.3, 1.7) 不是竞技场位置）【包，`fix_walks.txt`】。
- 遭遇与路线段的对应：boss 场景由场景包对象确认（`Tut_03` 的 BattleScene 与茧堆、`Bone_05_boss`、`Bone_East_12` 的 `Lace Boss1`、`Bone_East_08` 的 boss 附加场景、`Belltown_Shrine` 的 `Spinner Boss`、`Coral_Judge_Arena` 的 `Last Judge`、`Cog_Dancers`、`Library_13` 的 Trobbio、`Hang_04_boss`（14 波）、`Song_Tower_01`、`Cradle_03` 的 `Silk Boss`）【包】；B 类竞技场对应到哪个路线段是【推】（用社区房间名）。
- Lace 2 的入口【包 `fix_fsm_cogdancers_sequence.txt`】：`Cog_Dancers` 的 `Boss Scene` FSM `Sequence` 在第一次演奏（DESIGN 写的"Dancers 雕像处演奏 Threefold Melody"）结束时，经 `Break Lock Pt2` 置 `UnlockedMelodyLift` = 1 并存档，进入 `Idle Unlocked`（升降梯交互 `Lift Unlocked Inspect` 激活）。**以后再进这个房间**：`Check`（`defeatedCogworkDancers`）→ `Defeated` → 测 `UnlockedMelodyLift` → `UNLOCKED` → `Gates Opened` → `Wait for hero pos` → `Door Entry` → `Idle Unlocked`，与升降梯交互（`LIFT INSPECTED`）→ `Get In Lift Start`（同时预加载 `Song_Tower_01`）→ `In Lift` → `Lift Start`（升降梯动画 `Move Up`，到动画事件结束）→ `Lift Moving` → `Fade Down`（淡出等待，核查者解出约 2.5 s，我的导出器没解出这个浮点数）→ `Travel Instant`：切到 `Song_Tower_01` 的 `door_cutsceneEndLaceTower` (49.3, 100.0)，Lace 2 的位置 `door_cinematicEnd` (54.3, 99.0) 离它约 5 u。所以 **Lace 2 退出后不用重新演奏旋律，坐升降梯即可**；升降梯在房间底部 (40, 4) 附近（`door_arriveFromTower` (40.0, 3.9)），离 bot1 约 9 u。乘坐全程时长未测（几秒，主要是动画）【推】。`Song_Tower_01` 另一个出口 right1 通 `Tube_Hub`，那边是 Lace 2 之后才到的区域，不能用来回撤。

### 3.2 结果表

"现在"一栏：DESIGN 没有为每段指定工作台，所以这里写的是**按路线顺序推定**的、遭遇前最后一张路线一定经过的工作台【推】；没有可靠推定时只写 DESIGN 的预算 380 s。节省 = 现在 − 最佳（区间相减，取中值的量级）。

| 遭遇（段） | 类 | 最佳免费工作台（条件） | 回撤 | 最佳付费 | 回撤 | 现在（推定） | 现在的回撤 | 每次退出省 |
|---|---|---|---|---|---|---|---|---|
| Moss Mother（S01，`Tut_03`） | B | `Tut_03` 同房间（入口 right1 → 工作台 x 90 → 战斗 x 57） | 38 u，0 门，5–10 s | — | — | DESIGN S01 列了"工作台"，先后不明 | — | 0–？（确保战前坐） |
| Bell Beast（S03，`Bone_05`） | A | `Bone_04`（Marrow Map Shop），无条件 | 88 u，1 门，11–22 s | `Bone_01c` 30 | 260 u，3 门，34–67 s（更远） | S02 的 `Bonetown` 或 Mosshome `Mosstown_02c` | 238 u / 5 门，32–62 s；171 u / 4 门，23–45 s | **约 12–40 s** |
| Lace 1（S07，`Bone_East_12`） | A | `Room_Forge`（Deep Docks Forge，无条件；S06 的 Magma Bell 是 Forge 商店的 "Forge Lava Charm Tool"，110 + 1 Tool Metal【包 shopitems】，商店在这个房间【推】）。**同房间有 5 波竞技场**（`Battle Scene` (74.7, 12.3)，闸门 x = 58.5 / 89.5，`PersistentBoolItem`，清过一次就不再触发）【包 `fix_near_forge_battle.txt`】；社区逻辑把它放在左入口和工作台 / 商店（"forge daughter"）之间，第一次从左入口进来要先清它才能到工作台和 Magma Bell，工作台旁的 `Song_lever_side` (51.4, 32.0) 应是回左入口的闸门开关【攻】【推】，所以它多半就是 DESIGN S06 的"竞技场"。上去的气闸是 top1 处的 `dock_pipe_trapdoor (4)`（Trapdoor + `PersistentBoolItem`，上下各一个拉杆，`Lever Bottom` (39.0, 58.2)）【包】，从下方打拉杆应能打开并永久保持【推：拉杆事件接线未逐条核实】 | 97 u，1 门，13–25 s | `Dock_01` 30 | 204 u，2 门，26–52 s（更远） | `Bone_12`（Marrow Jail，S04） | 465 u，6 门，61–119 s | **约 48–94 s** |
| Fourth Chorus（S08，`Bone_East_08`，boss 在 (80.8, 7.5)） | A | `Bone_East_Umbrella`（Pinstress 小屋，`Bone_East_09` door1，门在包里常开、社区逻辑无要求【攻】，实际可用【未核实】） | 127 u，2 门，17–33 s | `Bellway_03` 30（路线 S08 本来就在这里开 Bellway 站） | 190 u，2 门，25–48 s | `Bellshrine_05`（S07 敲完 Deep Docks 钟） | 474 u，4 门，61–121 s | **约 44–88 s**（小屋）/ 36–73 s（买 `Bellway_03`） |
| Hunter's March 竞技场（S10，`Ant_04_mid`，5 波，闸门间中点 (199, 15)） | B | `Ant_17`（先打拉杆） | 264 u，3 门，35–68 s | `Bone_East_15` 30 | 338 u，5 门，45–87 s（更远） | — | 380 s（预算） | 拉杆 + 坐下是唯一选择 |
| Greymoor 钟 / 伏击（S11，`Bellshrine_02`） | B | `Greymoor_02`（East Bellshrine Room） | 48 u，1 门，7–13 s | — | — | — | — | — |
| Greymoor_04 塔（S11?，2 波） | B | `Halfway_01` | 78 u，2 门，11–20 s | — | — | — | — | — |
| Reaper 礼拜堂（S11 可选） | B | `Greymoor_08` 商队（要商队在 Greymoor） | 152 u，3 门，21–40 s | — | — | — | — | — |
| Shellwood 竞技场（S12，`Shellwood_01b`，3 波） | B | `Mosstown_03`（Greyroots） / `Belltown`（到过 Bellhart 后） | 355 u，4 门，46–91 s / 238 u，3 门，31–61 s | `Shellwood_01b` 40（同房间） | 37 u，0 门，5–9 s | — | — | 约 26–82 s |
| Widow（S13，`Belltown_Shrine`） | A | `Belltown` | 143 u，2 门，19–37 s | Bellhome（要两个许愿） | 170 u，3 门，23–44 s（更远） | `Belltown`（S13 到 Bellhart 一般会坐） | 同左 | 0（确保战前坐） |
| Last Judge（S17，`Coral_Judge_Arena`） | A | `Bonetown`（S15 → S17 路过；从 `Tut_01` 进来的 bot2 绕到工作台再去上方出口，比直走多约 50 u，6–13 s）；`Bellshrine_Coral` 免费但 S17 到不了（见下） | 872 u，5 门，111–220 s | `Bellway_08` 40（**条件买**，§4.2） | 337 u，3 门，44–86 s | `Weave_07`（S15 最后一张） | 1,203 u，10 门，155–306 s | 坐 `Bonetown`：约 44–86 s（对 `Weave_07`）；再买 `Bellway_08`：再省约 67–134 s |
| Dancers（S19，`Cog_Dancers`） | A | `Song_Enclave` L1（`enclaveLevel` ≥ 1）/ `Bellshrine_Enclave`（敲钟后） | 285 u，2 门，37–72 s / 335 u，3 门，43–85 s | — | — | Songclave（S18） | 同左 | 0（确保 S18 敲钟并坐） |
| Trobbio（S22，`Library_13`） | A | `Bellway_City`（Grand Bellway） | 119 u，2 门，16–31 s | — | — | `Library_08`（S21） | 248 u，3 门，33–64 s | **约 17–33 s** |
| Clawline 竞技场（S23，`Under_18`，7 波） | B | `Under_17` | 98 u，1 门，13–25 s | 收费椅 15/次 | 364 u，6 门（更远） | — | — | — |
| Underworks 西侧连战（S23?，`Under_07`） | B | `Under_07b` | 110 u，2 门，15–29 s | `Under_08` 收费椅 | 106 u，2 门，14–28 s | — | — | ≈ 0 |
| Forum（S25，`Hang_04`） | A | `Hang_06b`（Ventrica） | 139 u，2 门，18–36 s | — | — | `Hang_06b`（forum_route 方案） | 同左 | 0 |
| Lace 2（S26，`Song_Tower_01`） | A | `Cog_Bench` → `Cog_Dancers` 的升降梯（第一次演奏解锁后，§3.1）→ `Song_Tower_01` | 到升降梯 60 u，2 门，8–16 s；+ 乘梯（未测，几秒）+ 下梯到 Lace 约 5 u | — | — | S24 的 `Cog_Bench` | 同左 | 0（确保 S26 前在 `Cog_Bench` 坐） |
| GMS（S27，`Cradle_03`） | A | `Tube_Hub`（Terminus Ventrica，Lace 2 之后才到得了） | 128 u，1 门，16–32 s | — | — | `Tube_Hub`（S26 的 "Cradle 工作台"） | 同左 | 0 |
| 其他竞技场：`Bone_01`（4 波）/ `Dock_08`（7 波）/ `Cog_05`（6 波）/ `Song_07` 伏击 / `Library_02`（5–6 波）/ G&Z 切磋 `Library_09` / `Song_04`（5 波） | B | `Bonetown` 1 门 10–20 s / `Bone_12` 3 门 24–46 s / `Cog_Bench` 2 门 11–21 s / `Song_18` 2 门 17–32 s / `Song_Enclave` L1 1 门 10–19 s / `Library_08` 2 门 22–43 s / `Song_10` 1 门 5–9 s | | `Bone_01c` 30：5–10 s / `Dock_01` 30：8–16 s | | | | 付费只省 5–30 s |

补充：
- **Last Judge 的竖井**：`Bonetown` → `Coral_03` 底部约 430 u、3 门，然后在 `Coral_03` 里爬约 200 u（直线模型按直线算，实际更久，Blasted Steps 还有 DESIGN 说的 Steel Soul 变体房间）。`Bellway_08` 在 `Coral_03` 顶端 left1 旁（工作台离门 30 u），从它出发**完全跳过竖井**【包：门坐标】。
- **`Bellshrine_Coral`（Sands of Karak 钟塔，免费，离 Last Judge 3 门、217 u、29–56 s）在 S17 从下方到不了**：
  - 路径是 `Coral_32` top1 (143, 115.5) → `Coral_38` bot1 (63, −0.5) → `Coral_38` right1 (128.5, 77) → `Bellshrine_Coral`【包 `gates_all.json`】。
  - `Coral_38` 底部到 right1 要坐升降梯 `Hornet_cage_rect_lift`（x ≈ 24）。它的 `LiftControl` 有两个停靠点：停靠点 0 在上方 (y 75.2，默认停在这里)，**只有它的呼叫板 `Hornet_pressure_plate_small` (27.0, 73.0) 能解锁升降梯**（`CallPlateUnlocks` = 1）；停靠点 1 在下方 (y 7.2)，呼叫板 (27.0, 5.0) 不解锁（`CallPlateUnlocks` = 0）。解锁状态存在 `persistentUnlocked`（PersistentBoolItem）里【包 `fix_lift_coral38.txt`】【码 `LiftControl.cs:220-256`：有停靠点带 `CallPlateUnlocks` 时升降梯开局不解锁；`304-312`：只有这种停靠点的呼叫板接 `Unlock`；`500-505`：未解锁时 `MoveToStop` 直接返回】。所以必须先从上方（`Coral_26` 经 left1，或从 `Bellshrine_Coral` 经 right1）来过一次。社区逻辑也写 bottom ↔ right 只能靠 "Activate Elevator switch Karak"，从底部能爬到的只有一个死胡同小平台【攻】。
  - `Coral_32` 的 top1 前有一面 `Coral Crust Wall Tall` (138.7, 110.1)：`Control` FSM 挨 3 次攻击（`Hits` = 3，`ReceivedDamage` → 计数；没有 `Damageable Range` 子对象时任何方向的攻击都算）后永久碎掉（`PersistentBoolItem`）；`Direction Control` FSM 在从 top1 进场时关掉它的碰撞体【包 `fix_fsm_coral32_crustwall.txt`】【码 `DamageEnemies.cs:1215`：打到带 `IsCoralCrustWall` 的 Recoiler 会通知 FSM】。社区逻辑注明 top1 "Have to come from Coral_38 side"【攻】。墙本身可能从下方打得掉【推】，但上一条的升降梯已经堵死了这条路。
  - 路线在 S17 之前不去 Sands of Karak 上层（DESIGN §3.6.4），所以 `Bellshrine_Coral` 不是 S17 的选项。要用它就得在路线里加一段 Sands of Karak（经 `Coral_34` top1 要过 Great Conchflies，见下一条），不在本文范围。
- **`Room_Pinstress`（Blasted Steps 竖井中段旁的有条件工作台）在 Great Conchflies 的闸门后面**：从 `Coral_03` left2 (y 105) 出去是 `Coral_11` → `Coral_11b` → `Coral_34` door1 → `Room_Pinstress`。`Coral_11` 里有 Great Conchflies 的 `Boss Scene`，`Battle Gate Conch` 在 (40.0, 19.5)、(39.3, 19.1) 和 (69.9, 19.5)，挡住通往 left1 (40.5, 15) 的路【包 `fix_near_coral11.txt`】；社区逻辑写 left1 要 "defeat Boss: Great Conchflies"【攻】。DESIGN 把 Great Conchflies 列为永不交战，所以这张椅子也不是选项。它本身的条件：`Pinstress States` FSM 测 `hasChargeSlash`、`pinstressQuestReady`、`pinstressStoppedResting`、`pinstressInsideSitting` 选 NPC 的状态【包 `fix_fsm_room_pinstress.txt`】，哪个状态激活 `Room Regular Parent`（工作台所在）我的导出器没解清楚。`Coral_34` 的另一个出口 top1 通 Sands of Karak。
- **Dancers 没有付费选项**：`Cog_Bench` 在 Dancers 守着的 Cogwork Core 一侧，打完才到得了【推】；`Arborium_04`（Memorium）3 门 17–33 s，但 S19 时能否到达【未核实】。
- **Fourth Chorus 的两张椅子**：小屋免费且更近，但门能不能进没有实测；`Bellway_03` 钟椅 30 在路线本来要停的 Bellway 站房间里，绕路≈ 0，是可靠的后备。

## 4. 付费 / 有条件工作台的价值排序

### 4.1 公式与假设

价值（每局，秒）= Σ_附近遭遇 [ q_e × Δt_e + G_e ] − （绕路秒 + 购买 13–15 s + 念珠 ÷ r）

- Δt_e：该工作台比"没有它时路线会用的工作台"（**基线，必须是路线上免费可坐、且本方案也会坐的那张**）每次少走的单程回撤（§3.2，取区间中值）。
- q_e【推】：每局在该遭遇紧急退出的预期次数。DESIGN 的约 4.5 次 / 局按权重分摊：A 类 10 个（Bell Beast、Lace 1、Fourth Chorus、Widow、Last Judge、Dancers、Trobbio、Forum、Lace 2、GMS）权重 3，B 类约 10 个权重 1 → A 类每个 q ≈ 0.34，B 类每个 q ≈ 0.11。等 K1 / M2 的险情率出来后替换。
- G_e：交战门项，单独建模（初稿把它当成"每个 A 类再回工作台 0.5 次"，既与 DESIGN 的 700 s 对不上——那是 700 / 380 ≈ 1.8 次 / 局，不是 10 × 0.5 = 5 次——也忽略了坐在战前的工作台本来就满足交战门）。DESIGN §3.7.6 的交战门要求"在 playbook 指定的工作台休息过、满血"，所以从工作台走到战斗门口时只要挨了打，就要走回工作台再来。设 p_X = 从工作台 X 走到门口时不满足交战门的概率，T_X = 单程时间，每次"成功到达门口"的期望耗时是 T_X × (1 + p_X) / (1 − p_X)，其中多出的 2 T_X × p_X / (1 − p_X) 就是交战门回撤。每局要走 1 + q_e 次（第一次 + 每次退出后），所以
  G_e = (1 + q_e) × 2 × [ T_基线 × p_基线 / (1 − p_基线) − T_X × p_X / (1 − p_X) ]。
  p 没有任何实测【推】；DESIGN 的 700 s 先验折合每局约 1.8 次、约 20 个 A/B 单元，平均每个单元 p ≈ 0.09。
- r：念珠换成秒的汇率。DESIGN 没有刷念珠速率；按保守的 1 念珠/s（P10 收入不够时要去刷）计，同时给出路线有余钱（念珠成本近似 0）时的结果。

### 4.2 排序

| # | 工作台 | 价格 | 覆盖的遭遇 | Δt（中值） | 成本（r = 1） | 盈亏平衡 w* | 每局价值（只算退出 / 加交战门） | 结论 |
|---|---|---|---|---|---|---|---|---|
| 1 | `Bellway_08`（Blasted Steps） | 40 | Last Judge（A）+ 竖井上方的 Blasted Steps 路段 | ≈ 100 s（67–134 s，对路线免费坐的 `Bonetown`；直线模型低估竖井攀爬，实际可能更大） | 绕路约 12 s + 购买 14 s + 40 = 66 s（念珠有余时约 26 s） | 只算退出：q* = 0.66（念珠有余时 0.26） | 只算退出（q = 0.34）：**−32 s**（念珠有余时 +8 s）；加交战门项见下表 | **默认不买，按判据定**：买 ⇔ V = q_LJ × Δt + G − 成本 > 0（q_LJ 用实测值替换先验 0.34）；按下表，相当于 p ≥ 约 0.07，或 q_LJ ≥ 0.66，或 S17 念珠有余且 q_LJ ≥ 0.26。要买就在 S17 爬完 `Coral_03` 后进 `Bellway_08` 付 40、坐下，再去 Last Judge。它是 S17 时竖井上方唯一能到的存档点（`Bellshrine_Coral` 到不了，`Room_Pinstress` 在 Great Conchflies 后，§3.2） |
| 2 | `Bellway_03`（Far Fields） | 30 | Fourth Chorus（A） | 小屋可用时为负（比小屋远约 12 s）；小屋不可用时 ≈ 55 s（对 `Bellshrine_05`，36–73 s） | 绕路 0 + 14 + 30 = 44 s | q* = 0.81 | 小屋不可用时只算退出 −25 s；交战门项按同一公式，p（`Bellshrine_05` → Fourth Chorus，474 u）≥ 约 0.10 时转正 | **后备**：只在 Pinstress 小屋实测不可用时按判据决定 |
| 3 | `Shellwood_01b` | 40 | Shellwood 3 波竞技场（B）；Sister Splinter（默认跳过） | ≈ 39 s（对 Belltown）/ ≈ 61 s（对 Mosstown_03） | 绕路约 5 s + 14 + 40 = 59 s | 1.0–1.5 次 | 约 −53 s | 不买；如果 Sister Splinter 被迫开打（A 类）再评估 |
| 4 | `Dock_01` | 30 | `Dock_08` 7 波竞技场（B）；Lace 1 不如 `Room_Forge` | ≈ 23 s | 44 s | 1.9 次 | −41 s | 不买 |
| 5 | `Bone_01c` | 30 | `Bone_01` 4 波竞技场（B）；Bell Beast 不如 `Bone_04` | ≈ 7 s | 44 s | 6 次 | −43 s | 不买 |
| 6 | `Coral_02` | 60 | Last Judge 不如 `Bellway_08` | — | — | — | 负 | 不买 |
| 7 | Underworks 收费椅 | 15 / 次 | `Under_07` / `Under_10` | ≈ 0（`Under_07b`、`Under_17` 免费且一样近） | 每次 15 | — | 负 | 不用 |
| 8 | `Shellwood_08c`、`Bone_East_15`、`Dust_10`、`Bellway_Peak`、`Bellway_Aqueduct`、`Bellway_Shadow`、Bellhome | 30–60 / 许愿 | 路线上没有更近的 A 类遭遇 | — | — | — | — | 不买 |
| — | **有条件但免费**：`Ant_17` 拉杆 | 0 | Hunter's March 竞技场、整个 S10 | 唯一的工作台 | 拉杆往返约 36 u，5–9 s | — | 正 | **做**：先打拉杆再坐，避免 2 伤害的镰刀 |
| — | **有条件但免费**：钟塔工作台 | 0 | 敲钟后的下一段 | — | 0（就在钟旁） | — | 正 | 敲完钟顺手坐（Songclave 钟是 Dancers 的最佳选项之一） |

**`Bellway_08` 的交战门项**【推】：p = 从 `Bonetown` 出发、爬完竖井到 Last Judge 门口时不满足交战门的概率；保守地取 p_Bellway_08 = 0（两条路共用竖井顶端到竞技场那一段，那一段的挨打对从 `Bonetown` 出发更贵，计入只会让买更划算）。T_Bonetown = 165 s，q = 0.34，G = 1.34 × 330 × p / (1 − p)。

| p | G | 每局价值（r = 1） | 每局价值（念珠有余） |
|---|---|---|---|
| 0 | 0 | −32 s | +8 s |
| 0.05 | +23 s | −9 s | +31 s |
| 0.067 | +32 s | 0 | +40 s |
| 0.09（DESIGN 700 s 折合的平均值） | +44 s | +12 s | +52 s |
| 0.20 | +111 s | +79 s | +119 s |

所以三个量决定结论：Last Judge 的 q（K1/M2）、p（M5 oracle 在 S17 记录"从 `Bonetown` 醒来走到 Last Judge 门口时是否满血"）、S17 时念珠是否有余（M5 的 P10 收入）。在这些实测出来之前，路线表**不写**这次购买（DESIGN 的保守默认：不花念珠、不多一个约 5 s 不能暂停的窗口）；如果 Bind 可以替代走回工作台（交战门允许在门口 Bind 回满），p 的影响还会变小。

念珠合计：默认不变；如果按判据买 `Bellway_08`，+40（DESIGN §3.6.5 的约 1,200–1,600，forum_route 再加 350，合计约 1,590–1,990）。

## 5. 免费的节省：路线经过、难战前应坐下的工作台

都在路线自然路径上或旁边一两个房间【估】，不花念珠，绕路几秒到十几秒，坐下同时存档并补满血、丝和工具（交战门的门槛也就满足了，只要走到战斗门口前没挨打；挨打的概率按 §4.1 的 p 算）。

| 段 | 在哪坐 | 为了 | 备注 |
|---|---|---|---|
| S01 | `Tut_03` 工作台（Moss Mother 竞技场之前，同房间） | Moss Mother | 工作台在入口和战斗之间 |
| S03 | `Bone_04`（Marrow Map Shop） | Bell Beast | 上门 top1 就是 `Bone_05` |
| S04 | 敲 Marrow 钟后 `Bellshrine` | S04 扫荡 | 钟塔工作台敲钟后出现 |
| S06 → S07 | `Room_Forge`（先清同房间的 5 波竞技场，再买 Magma Bell、坐） | Lace 1 | 竞技场清过一次永久不再触发；上方 top1 的气闸（`dock_pipe_trapdoor (4)`，下侧有拉杆）通 `Bone_East_12`（§3.2） |
| S07 → S08 | `Bellshrine_05`（敲完 Deep Docks 钟） | Far Fields 路段 | — |
| S08 | `Bone_East_Umbrella`（`Bone_East_09` 的小屋） | Fourth Chorus | 小屋不可用时按 §4.2 判据决定是否买 `Bellway_03`（30） |
| S10 | `Ant_17`：先打左侧拉杆再坐 | Hunter's March 竞技场 | 不打拉杆坐下会挨 2 伤害且不设重生点 |
| S11 | `Greymoor_02`（钟塔隔壁）；`Halfway_01` | Greymoor 钟伏击、Greymoor_04、Garmond（`Greymoor_05` 28–55 s） | — |
| S13 | `Belltown` | Widow | — |
| S17 | 路过 `Bonetown` 坐一次（绕路约 6–13 s） | Last Judge | `Bellway_08`（40）默认不买，按 §4.2 判据在 K1/M2/M5 后决定 |
| S18 → S19 | 敲 Songclave 钟后 `Bellshrine_Enclave`，或 `enclaveLevel` ≥ 1 后的 Level 1 工作台 | Dancers | 与 forum_route 的 S18 提案一致 |
| S21 | `Library_08` 或 Songclave | G&Z 切磋、`Library_02` 连战 | forum_route §3.2 |
| S22 | `Bellway_City`（Grand Bellway） | Trobbio | — |
| S23 | `Under_17`；`Under_07b` | Clawline 竞技场；西侧连战 | 收费椅不用 |
| S25 | `Hang_06b` | Forum | forum_route |
| S26 | `Cog_Bench` | Lace 2（第一次在 `Cog_Dancers` 演奏旋律解锁升降梯；退出后坐升降梯回来） | 演奏前坐；演奏过场里有不能暂停、不能存档退出的窗口（§1.3） |
| S27 | `Tube_Hub` | GMS | DESIGN 已有 |

另外：章节边界（DESIGN §3.6.1，每章以"坐工作台 + 退出"结束）应尽量放在这些工作台上。

## 6. 对时间预算的影响【估】【推】

- 按门距模型（修订后的坐标），上面的安排下 A 类战斗的单程回撤：Bell Beast 11–22 s、Lace 1 13–25 s、Fourth Chorus 17–33 s、Widow 19–37 s、Dancers 37–85 s、Trobbio 16–31 s、Forum 18–36 s、Lace 2 8–16 s + 乘梯几秒、GMS 16–32 s；**合起来约 10–85 s**。Last Judge 单列：从 `Bonetown` 111–220 s（按 §4.2 判据买了 `Bellway_08` 时 44–86 s）。本文其他地方引用每次退出的回撤时都用这一组数。
- 没算进去的：Continue 后工作台场景加载 + 醒来（P7 待测，DESIGN §3.6.6 已注明）、boss 进场过场（各 boss 不同，未测）、重新清场（DESIGN §3.7.5 第 6 步）、模型低估的攀爬（竖井、平台）和能力 / 单向门造成的绕行。
- 所以 DESIGN §3.6.6 的"紧急退出恢复 1,700 s（暂定）"和"交战门的工作台回撤 700 s"**可能**偏高，但这只是**假设**：上面的数字来自不看能力、单向门和过场的直线模型，不能用来改预算。建议 M5 的 oracle 路线实测里给每个 A 类遭遇记录两项计时时间：①"从路线工作台醒来到进入战斗"（替换 380 s）；②"从工作台走到门口时是否满足交战门"（给出 §4.1 的 p，替换 700 s 的先验）。

## 7. DESIGN §3.6.4 提议文本（DESIGN 未改，由你和 lead 决定）

把 §3.6.4 "付费 / 有条件的工作台" 那一条替换为：

> - **工作台（2026-10-03 调研，[`research/benches.md`](research/benches.md)）：** 全游戏 80 个场景有可用工作台；付费的是钟椅（一次 30 / 40 / 60 念珠）、Underworks 收费椅（每次 15）和 Pilgrim's Rest 的收费门（30）。坐下即设置存档退出后的重生点（假椅除外）。购买期间约 5 s 不能暂停（BlockingInteractable），只在无威胁、GREEN、满血时确认。
>   - **免费规则（必做）：** 每个 A 类遭遇（及 Moss Mother）前在最近的工作台坐下：Moss Mother `Tut_03`、Bell Beast `Bone_04`、Lace 1 `Room_Forge`、Fourth Chorus `Bone_East_Umbrella`、Widow `Belltown`、Dancers `Bellshrine_Enclave` 或 Songclave Level 1、Trobbio `Bellway_City`、Forum `Hang_06b`、Lace 2 `Cog_Bench`、GMS `Tube_Hub`；B 类：Hunter's March `Ant_17`（**先打拉杆**再坐）、Greymoor `Greymoor_02`、Underworks `Under_17`。敲钟后顺手坐钟塔工作台。route_check 断言每个 A 类遭遇之前最后一次坐的工作台就是表里那张。
>   - **购买（默认不买，按判据定）：** `Bellway_08` 钟椅（40，Blasted Steps 竖井顶端）比路线上免费坐的 `Bonetown` 每次回撤少约 100 s。买 ⇔ q_LJ × 100 + G − 成本 > 0，成本约 66 s（念珠要刷时）或 26 s（念珠有余时），G = (1 + q_LJ) × 330 × p / (1 − p)，p = 从 `Bonetown` 走到 Last Judge 门口时不满足交战门的概率（benches.md §4）。q_LJ 来自 K1/M2，p 和 S17 念珠余量来自 M5 oracle；实测前路线表不写这次购买。要买就在 S17 爬完 `Coral_03` 后买、坐下，再去 Last Judge。附近的 `Bellshrine_Coral` 在 S17 到不了，`Room_Pinstress` 在 Great Conchflies 后面。
>   - **后备：** `Bone_East_Umbrella` 实测不可用时，S08 在 `Bellway_03`（30）按同一判据决定是否买钟椅。
>   - **不买：** 其余钟椅和收费椅（附近有同样近的免费工作台，或附近没有要打的 A 类遭遇）；Bellhome。
>   - **不买地图**：导航用离线提取的世界图（§3.4）。

§3.6.4 路线表相应几格（只列新增内容）：

- S01 内容加："Moss Mother 前坐 `Tut_03` 工作台"。
- S03 加："Bell Beast 前坐 `Bone_04` 工作台"。
- S06/S07 加："`Room_Forge` 的 5 波竞技场清完后买 Magma Bell、坐 `Room_Forge` 工作台，经上方气闸（下侧拉杆）去 Lace 1"；route_check 要确认这个竞技场是不是 S06 的"竞技场"。
- S08 加："Fourth Chorus 前坐 `Bone_East_09` 小屋工作台（`Bone_East_Umbrella`）；不可用时按判据决定是否在 Bellway 站买钟椅 30"。
- S10 加："`Ant_17` 是陷阱椅：先打拉杆（置 `antBenchTrapDefused`），再坐"。
- S13 加："Widow 前坐 `Belltown`"。
- S17 加："途经 `Bonetown` 坐一次（约 +10 s）；然后 Grand Gate → Last Judge"。按判据要买 `Bellway_08` 时再加"爬完 `Coral_03` 后进 `Bellway_08` 买钟椅（40）坐下"，P50/P90 约 +30 / +45 s。
- S18 加（与 forum_route 一致）："敲 Songclave 钟，Dancers 前坐 `Bellshrine_Enclave`"。
- S22 加："Trobbio 前坐 `Bellway_City`"。
- S23 加："Clawline 竞技场前坐 `Under_17`"。
- S26 加："演奏 Threefold Melody 前坐 `Cog_Bench`；Lace 2 退出后从 `Cog_Dancers` 坐升降梯回 `Song_Tower_01`，不用重新演奏"。

§3.6.5 经济：念珠注明"`Bellway_08` 钟椅 40、`Bellway_03` 30 是按判据的可选项，默认不计"。§3.6.6：在紧急退出那一行注明"每次退出的回撤待 M5 oracle 实测（benches.md §6 的直线模型给出约 10–85 s、Last Judge 110–220 s，只作假设）"，交战门那一行注明"按每个单元的 p 实测"。§3.7.5 / quit map：加"收费机交互约 5 s 不能暂停"和"`Cog_Dancers` 一次性解锁过场：`Needolin Prompted Full` 到 `Return Control` 不能暂停，`Break Lock Pt1` 到 `Pt2` 不能存档退出"。

## 8. 待实测 / 未核实

1. `Bone_East_09` 的小屋门（`Bone_East_Umbrella`）在 S08 时能否进入、工作台能否坐。
2. 收费流程实测：按"是"到可以暂停的时长；受击取消；钟椅升起时长；之后存档退出 → Continue 是否在钟椅上醒来。
3. `Ant_17`：拉杆位置和打法；不打拉杆坐下的伤害（2）是否会被 Fractured Mask 抵挡；DESIGN S10 "在该工作台休息前买 [待验证原因]" 是否与这个陷阱有关【推】。
4. `Room_Forge` 上方气闸（社区逻辑 "Open Airlock Up"）：包里是 top1 处的 `dock_pipe_trapdoor (4)`，下侧有 `Lever Bottom`【包】；待实测从下方打拉杆能否打开。另外核对 `Room_Forge` 的 5 波竞技场是否就是 DESIGN S06 的"竞技场"、`Song_lever_side` 是否是回左入口的闸门开关。
5. Lace 2 退出后的回程：已由包确认是 `Cog_Dancers` 的升降梯（`UnlockedMelodyLift`，§3.1），待测乘梯全程时长，以及一次性解锁过场里不能暂停、不能存档退出的两个窗口各多长（§1.3）。
6. 各 boss 的进场过场时长；每个 A 类遭遇"从路线工作台醒来到开打"的实测计时（替换 §3 的模型），以及"走到门口时是否满足交战门"（§4.1 的 p，尤其是 `Bonetown` → Last Judge）。
7. `Greymoor_08` 商队何时到 Greymoor（`Bone_10` 商队的 `QUEST END TRAVEL` 由哪个 quest 触发）。
8. ~~`Bellshrine_Coral` 在 S17 能否经 `Coral_38` 到达~~：已由包确认不能（升降梯只有上方呼叫板能解锁，§3.2）。只有路线加一段 Sands of Karak 上层时才需要再看。
9. `Shellwood_01b` 3 波 BattleScene 在房间里的实际位置（包里的坐标是预制体默认值），以及它是不是 DESIGN S12 说的 Shellwood 竞技场。
10. §4 的 q、p、r 全是先验，等 K1/M2 的险情率、M5 的交战门记录和路线念珠实测替换；`Bellway_08` / `Bellway_03` 买不买由它们代入 §4.2 判据决定。

## 附录 A：全部工作台对象（100 个）

由 `gen_table.py` 从 `bench_scan.jsonl`、`bench_extra.txt` 和社区房间图生成【包】（区域 / 房间名【攻】）。"激活链"从对象自身到根，1 = 在包里激活、0 = 未激活（由 TestGameObjectActivator 等在运行时切换）。Black Thread 的 "Normal World" 父对象在包里未激活、第一、二幕由 `blackThreadWorld` 测试打开，这种情况算"免费"。

| 场景 | 区域 / 房间 | 对象 | 坐标 | 激活链 | 类 | 价格 | 自动备注 |
|---|---|---|---|---|---|---|---|
| clover_20 | ? / ? | `RestBench` | (127.5, 16.8) | 1 | 免费 |  |  |
| dust_maze_09_entrance | ? / ? | `RestBench` | (21.0, 3.9) | 0 | 不可用 |  | RestBench 在包里未激活，场景内没有激活它的对象 |
| tut_04 | ? / ? | `States/Intro Scene/Snail Shamans Set/RestBench` | (47.8, 5.8) | 1101 | 有条件 |  | Snail Shamans 场景，按 `CompletedRedMemory` 切换 Intro/Outro |
| tut_04 | ? / ? | `States/Outro Scene/RestBench` | (47.8, 5.8) | 101 | 有条件 |  | Snail Shamans 场景，按 `CompletedRedMemory` 切换 Intro/Outro |
| Belltown | bellhart / Belltown | `RestBench` | (68.9, 6.3) | 1 | 免费 |  |  |
| Belltown_Shrine | bellhart / Widow Boss Fight | `…nt/Normal World/Boss Scene/Bell Bench/RestBench` | (52.8, 9.9) | 11101 | 有条件 |  | 在 Widow 的 Boss Scene 下，打完 Widow 敲钟后出现（推） |
| Belltown_room_spare | bellhart / Bellhome | `furnishings/bed/RestBench` | (27.8, 6.8) | 111 | 有条件 |  | Bellhome：`Belltown` 的 `Hornet House States/door5` 只在 `BelltownHouseState`=Full 时激活；Half/Full 由 TimePasses 在 Bellhart 以外按 quest 'Belltown House Start' / 'Belltown House Mid' 完成推进（GameManager.cs:1734-1749） |
| Bellway_Shadow | bilewater / Bilewater Bellway | `Shadow_09b/bell_bench/RestBench` | (37.5, 23.1) | 111 | 付费 | 60（Bell Bench Toll Upperlands） | 钟椅收费机，付一次永久升起（`bell_toll_machine` 的 PersistentBoolItem） |
| Organ_01 | bilewater / Exhaust Organ Interior | `Organ Webbed Bench/clean_bench/RestBench` | (52.3, 30.4) | 101 | 有条件 |  | 先打掉 `Organ Webbed Bench`（Breakable + PersistentBoolItem）才有 `clean_bench` |
| Shadow_08 | bilewater / Bilewater East Bench | `RestBench` | (22.9, 6.8) | 1 | 免费 |  |  |
| Shadow_15 | bilewater / Bilewater Bullshit Bench | `Fake Bench Collapser/RestBench` | (14.2, 45.9) | 11 | 假椅 |  | z_FakeBench=1：不设重生点; `Fake Bench Collapser`：坐上去会塌 |
| Shadow_18 | bilewater / Bilewater Groal Arena | `RestBench` | (61.1, 10.7) | 1 | 免费 |  |  |
| Bellway_08 | blasted-steps / Blasted Steps Bellway | `Bell Bench Scene/bell_bench/RestBench` | (120.6, 14.0) | 111 | 付费 | 40（Bell Bench Toll Midlands） | 钟椅收费机，付一次永久升起（`bell_toll_machine` 的 PersistentBoolItem）；付后另置 `activatedStepsUpperBellbench` |
| Coral_02 | blasted-steps / Blasted Steps Toll Bench Bottom | `bell_bench/RestBench` | (195.9, 5.1) | 11 | 付费 | 60（Bellway Toll Midlands） | 钟椅收费机，付一次永久升起（`bell_toll_machine` 的 PersistentBoolItem）（引用的价格资产是 Bellway Toll Midlands） |
| Coral_Judge_Arena | blasted-steps / Last Judge Arena | `…van_Set/Caravan/Caravan Scenery/Bench/RestBench` | (23.2, 23.7) | 11101 | 有条件 |  | `CaravanTroupeLocation` = CoralJudge(2) 且 `defeatedLastJudge` |
| Room_Pinstress | blasted-steps / Windy Pinstress Room | `Pinstress States/Room Regular Parent/RestBench` | (22.3, 6.6) | 101 | 有条件 |  | `Pinstress States` FSM 测 `hasChargeSlash`、`pinstressQuestReady`、`pinstressStoppedResting`、`pinstressInsideSitting` 选状态，哪个状态激活 `Room Regular Parent` 未解清；从路线进来要过 `Coral_11` 的 Great Conchflies 闸门（§3.2） |
| Bonetown | bone-bottom / Bone Bottom Town | `…States/Normal World/RestBench Control/RestBench` | (238.8, 6.9) | 1101 | 免费 |  | `skullKingInvaded` 时被 `Break Bench` 打坏、`skullKingBenchMended`/`skullKingKilled` 后修好；入侵要先 `skullKingDefeated`（GameManager.cs:1626），本路线不打 Skull Tyrant，所以一直可用 |
| Bonetown（`bonetown_boss`） | bone-bottom / Bone Bottom Town | `Skull King Encounter - deprecated?/Fake Bench` | (238.6, 6.9) | 00 | 不可用 |  | 废弃的 Skull King 遭遇对象（未激活） |
| Mosstown_02c | bone-bottom / Mosshome Druid | `RestBench` | (13.0, 2.7) | 1 | 免费 |  |  |
| Bellshrine_Enclave | choral-chambers / Songclave Bellshrine | `Whole Scene/Bell Bench/RestBench` | (28.5, 5.2) | 111 | 有条件 |  | 敲 Songclave 钟后出现（forum_route §1.1） |
| Bellway_City | choral-chambers / Grand Bellway | `Group/RestBench` | (67.7, 11.6) | 11 | 免费 |  |  |
| Hang_01 | choral-chambers / High Halls Entrance | `RestBench` | (13.0, 11.4) | 1 | 免费 |  |  |
| Song_01b | choral-chambers / Choral Chambers Ventrica Room | `GameObject (3)/RestBench` | (14.9, 3.5) | 01 | 不可用 |  | RestBench 在包里未激活，场景内没有对象引用它（refscan） |
| Song_10 | choral-chambers / Choral Chambers Spa | `RestBench` | (30.6, 42.6) | 1 | 免费 |  |  |
| Song_18 | choral-chambers / Choral Chambers Below Dining | `RestBench` | (16.5, 57.7) | 1 | 免费 |  |  |
| Song_Enclave | choral-chambers / Songclave | `…Black Thread World/Enclave Act 3/Town/RestBench` | (38.8, 6.7) | 11101 | 第三幕变体 |  |  |
| Song_Enclave | choral-chambers / Songclave | `…l World/Enclave States/States/Level 1/RestBench` | (38.8, 6.7) | 101101 | 有条件 |  | `enclaveLevel` ≥ 1（forum_route §1.1） |
| Under_07b | choral-chambers / Choral Chambers Outisde Underworks | `RestBench` | (43.6, 80.7) | 1 | 免费 |  |  |
| Cog_Bench | cogwork-core / Cogwork Core Bench & Map | `RestBench` | (24.2, 7.8) | 1 | 免费 |  |  |
| Bellshrine_05 | deep-docks / Deep Docks Bellshrine | `Whole Scene/Bell Bench/RestBench` | (20.5, 5.2) | 111 | 有条件 |  | 敲钟后升起（同 Bellshrine 预制体，推） |
| Dock_01 | deep-docks / Deep Docks Bench Shaft | `bell_bench (1)/RestBench` | (19.2, 65.0) | 11 | 付费 | 30（Bell Bench Toll Lowlands） | 钟椅收费机，付一次永久升起（`bell_toll_machine` 的 PersistentBoolItem） |
| Dock_06_Church | deep-docks / Deep Docks Church | `Group/RestBench (1)` | (22.2, 3.9) | 11 | 免费 |  |  |
| Dock_10 | deep-docks / Deep Docks Sauna | `RestBench` | (17.5, 29.8) | 1 | 免费 |  |  |
| Room_Diving_Bell | deep-docks / Deep Docks Diving Bell Interior | `Travel Sequence Control/RestBench` | (26.0, 6.7) | 11 | 假椅 |  | z_FakeBench=1：不设重生点; 潜水钟旅行座位 |
| Room_Forge | deep-docks / Deep Docks Forge | `RestBench` | (58.5, 31.9) | 1 | 免费 |  |  |
| Bellway_03 | far-fields / Far Fields Bellway | `bell_bench/RestBench` | (49.4, 10.0) | 11 | 付费 | 30（Bell Bench Toll Lowlands） | 钟椅收费机，付一次永久升起（`bell_toll_machine` 的 PersistentBoolItem） |
| Bone_East_10_Room | far-fields / Far Fields Pilgrim's Rest Shop | `RestBench` | (53.4, 12.5) | 1 | 有条件 |  | 在 Pilgrim's Rest 内：`Bone_East_10` 的收费门 30（Pilgrims Rest Door），或被 Rhino 撞开（`PilgrimsRestDoorBroken`） |
| Bone_East_15 | far-fields / Far Fields Deep Docks Loopback | `bell_bench/RestBench` | (35.4, 54.0) | 11 | 付费 | 30（Bell Bench Toll Lowlands） | 钟椅收费机，付一次永久升起（`bell_toll_machine` 的 PersistentBoolItem） |
| Bone_East_18b | far-fields / Far Fields Deep Lower East | `Group(Split)/Group (4)/TrapBench` | (172.2, 78.8) | 011 | 假椅 |  | z_FakeBench=1：不设重生点; Set Respawn=0; Boss Scene 的陷阱椅（按某个 quest 已接受激活） |
| Bone_East_26 | far-fields / Far Fields Deep Fort Passage | `Group(Split)/Group (4)/TrapBench` | (172.2, 78.8) | 011 | 假椅 |  | z_FakeBench=1：不设重生点; Set Respawn=0; Boss Scene 的陷阱椅（按某个 quest 已接受激活） |
| Bone_East_27 | far-fields / Far Fields Deep Fort Bench | `RestBench` | (24.0, 47.0) | 1 | 免费 |  |  |
| Bone_East_Umbrella | far-fields / Far Fields Pinstress Hut Interior | `RestBench` | (20.2, 6.6) | 1 | 免费 |  |  |
| Bone_East_Weavehome | far-fields / Weavenest Cindril Entrance | `RestBench` | (39.2, 92.7) | 1 | 免费 |  |  |
| Sprintmaster_Cave | far-fields / Sprintmaster Cave | `…rintmaster Race Inactive Folder/Bench/RestBench` | (49.6, 13.0) | 1111 | 免费 |  |  |
| Bellshrine_02 | greymoor / Greymoor Bellshrine | `Whole Scene/Bell Bench/RestBench` | (20.5, 5.2) | 111 | 有条件 |  | 敲钟后升起（同 Bellshrine 预制体，推） |
| Greymoor_02 | greymoor / Greymoor East Bellshrine Room | `RestBench` | (62.3, 4.7) | 1 | 免费 |  |  |
| Greymoor_08（`greymoor_08_caravan`） | greymoor / Greymoor Entry to Bellhart | `Caravan/Bench/RestBench` | (43.9, 4.2) | 111 | 有条件 |  | 附加场景只在 `CaravanTroupeLocation` = Greymoor(1) 时加载（`Caravan Scene Loader`） |
| Halfway_01 | greymoor / Greymoor Halfway Home | `RestBench` | (45.8, 9.9) | 1 | 免费 |  |  |
| Hang_06b | high-halls / High Halls Ventrica | `new_scene/RestBench` | (12.8, 3.5) | 11 | 免费 |  |  |
| Ant_17 | hunter-s-march / Hunter's March Trapped Bench | `Trap Scene/RestBench` | (29.0, 5.9) | 11 | 有条件 |  | Bench Control 只在 `antBenchTrapDefused` 为真时可用; 陷阱椅：拉杆 `ant_lever_persistent`（11.0, 8.7）置 `antBenchTrapDefused` 前坐下会触发 `Hunter Sickle Trap`（伤害 2） |
| Arborium_04 | memorium / Memorium bench | `RestBench` | (11.7, 6.5) | 1 | 免费 |  |  |
| Tut_03 | moss-grotto / Ruined Chapel | `RestBench` | (90.4, 3.7) | 1 | 免费 |  |  |
| Bellway_Peak | mount-fay / Mount Fay Bench Toll | `bell_bench/RestBench` | (14.4, 6.1) | 11 | 付费 | 60（Bellway Toll Midlands） | 钟椅收费机，付一次永久升起（`bell_toll_machine` 的 PersistentBoolItem） |
| Peak_02 | mount-fay / Mount Fay Shakra | `mapper_bits/RestBench` | (65.7, 7.9) | 11 | 免费 |  |  |
| Peak_07 | mount-fay / Mount Fay Right Side Middle Room | `RestBench` | (11.1, 6.0) | 1 | 免费 |  |  |
| Peak_12 | mount-fay / Mount Fay Peak Bench | `RestBench (1)` | (21.6, 4.6) | 1 | 免费 |  |  |
| Aqueduct_05（`aqueduct_05_festival`） | putrified-ducts / Fleatopia | `…Flea Festival/Festival_Feast/RestBench Festival` | (124.3, 9.1) | 1111 | 有条件 |  | 跳蚤商队到 Aqueduct 后（Flea Festival），第三幕内容 |
| Aqueduct_05（`aqueduct_05_caravan`） | putrified-ducts / Fleatopia | `Caravan_States/Fleatopia/RestBench` | (115.3, 9.1) | 111 | 有条件 |  | 跳蚤商队到 Aqueduct 后（Fleatopia），第三幕内容 |
| Aqueduct_05（`aqueduct_05_pre`） | putrified-ducts / Fleatopia | `Caravan_States/Pre_Fleatopia/RestBench` | (106.6, 8.3) | 111 | 有条件 |  | 跳蚤商队到 Aqueduct 后（Pre_Fleatopia），第三幕内容 |
| Bellway_Aqueduct | putrified-ducts / Putrified Ducts Bellway | `Shadow_09b/bell_bench/RestBench` | (83.6, 23.0) | 111 | 付费 | 60（Bell Bench Toll Upperlands） | 钟椅收费机，付一次永久升起（`bell_toll_machine` 的 PersistentBoolItem） |
| Room_Huntress | putrified-ducts / Huntress | `RestBench` | (13.4, 5.8) | 1 | 免费 |  |  |
| Bellshrine_Coral | sands-of-karak / Sands of Karak Bellshrine | `RestBench` | (26.9, 15.5) | 1 | 免费 |  | 从下方（`Coral_32` top1 → `Coral_38`）要先在上方解锁 `Coral_38` 的升降梯（§3.2） |
| Coral_Tower_01 | sands-of-karak / Coral Tower | `RestBench` | (126.5, 8.5) | 1 | 免费 |  |  |
| Bellshrine_03 | shellwood / Shellwood Bellshrine | `Whole Scene/Bell Bench/RestBench` | (20.5, 5.2) | 111 | 有条件 |  | 敲钟后升起（同 Bellshrine 预制体，推） |
| Mosstown_03 | shellwood / Greyroots Basement Tall room | `RestBench` | (13.7, 56.1) | 1 | 免费 |  |  |
| Shellwood_01b | shellwood / Shellwood Sister Splinter Bench | `bell_bench/RestBench` | (23.3, 37.1) | 11 | 付费 | 40（Bell Bench Toll Midlands） | 钟椅收费机，付一次永久升起（`bell_toll_machine` 的 PersistentBoolItem）；同房间有 3 波 BattleScene |
| Shellwood_08c | shellwood / Shellwood Lower Toll bench | `bell_bench/RestBench` | (14.9, 5.1) | 11 | 付费 | 40（Bell Bench Toll Midlands） | 钟椅收费机，付一次永久升起（`bell_toll_machine` 的 PersistentBoolItem） |
| Dust_10 | sinner-s-road / Sinner's Road Bench | `bell_bench Group/bell_bench/RestBench` | (122.2, 45.0) | 111 | 付费+有条件 | 40（Bell Bench Toll Midlands） | 钟椅收费机，付一次永久升起（`bell_toll_machine` 的 PersistentBoolItem）；另需 `FixedDustBellBench`（坏椅，BellBench.fixedPDBool） |
| Dust_11 | sinner-s-road / Sinner's Road Styx Room | `Steel Soul States/Regular/NPC Control/RestBench` | (111.0, 2.8) | 1101 | 有条件 |  | 普通模式对象（钢铁之魂下不出现） |
| Dust_11 | sinner-s-road / Sinner's Road Styx Room | `Steel Soul States/Steel Soul/RestBench (1)` | (110.0, 2.8) | 101 | 免费 |  | 钢铁之魂专用对象（`permadeathMode` 测试） |
| Abyss_09 | the-abyss / Abyss Escape | `RestBench` | (8.0, 5.8) | 1 | 免费 |  |  |
| Abyss_12 | the-abyss / Abyss Final Bench | `RestBench` | (17.1, 7.6) | 1 | 免费 |  |  |
| Room_Diving_Bell_Abyss | the-abyss / Abyss Diving Bell Broken | `Wake Up Scene/RestBench` | (26.0, 6.7) | 11 | 免费 |  |  |
| Room_Diving_Bell_Abyss_Fixed | the-abyss / Abyss Diving Bell Fixed | `Travel Sequence Control/RestBench` | (26.0, 6.7) | 11 | 假椅 |  | z_FakeBench=1：不设重生点; 潜水钟旅行座位 |
| Cradle_Destroyed_Challenge_Bench | the-cradle / Path of Pain Bench | `RestBench` | (35.2, 4.8) | 1 | 免费 |  |  |
| Tube_Hub | the-cradle / Terminus Ventrica | `RestBench` | (102.4, 38.6) | 1 | 免费 |  |  |
| Bellshrine | the-marrow / The Marrow Bellshrine | `Whole Scene/Bell Bench/RestBench` | (20.5, 5.2) | 111 | 有条件 |  | 敲钟后由 Bellshrine Sequence 升起（Bellshrine_Enclave 已逐状态核实，其余同一预制体，推） |
| Bone_01c | the-marrow / The Marrow Bell Bench | `bell_bench/RestBench` | (168.3, 8.0) | 11 | 付费 | 30（Bell Bench Toll Lowlands） | 钟椅收费机，付一次永久升起（`bell_toll_machine` 的 PersistentBoolItem） |
| Bone_04 | the-marrow / The Marrow Map Shop | `RestBench` | (11.8, 17.9) | 1 | 免费 |  |  |
| Bone_10 | the-marrow / The Marrow Flea Caravan | `…lack Thread World/bonetown_exile_camp/RestBench` | (25.7, 15.0) | 1101 | 第三幕变体 |  |  |
| Bone_10 | the-marrow / The Marrow Flea Caravan | `…l World/Caravan/Caravan State Regular/RestBench` | (24.6, 15.4) | 11101 | 有条件 |  | `Caravan` 带 DeactivatePlayerDataTest：`CaravanTroupeLocation` = Bone(0) 时才在 |
| Bone_12 | the-marrow / The Marrow Jail | `… Thread States/Black Thread World/RestBench (1)` | (15.8, 3.5) | 101 | 第三幕变体 |  |  |
| Bone_12 | the-marrow / The Marrow Jail | `…/Normal World/Pin Gallery States/Here/RestBench` | (15.8, 3.5) | 10101 | 免费 |  | Pin Gallery 的 Here/Not Here 两个状态各有一张，总有一张在 |
| Bone_12 | the-marrow / The Marrow Jail | `…mal World/Pin Gallery States/Not Here/RestBench` | (18.6, 3.5) | 10101 | 免费 |  | Pin Gallery 的 Here/Not Here 两个状态各有一张，总有一张在 |
| Slab_06 | the-slab / Slab Bellway | `RestBench` | (92.3, 8.6) | 1 | 免费 |  |  |
| Slab_16 | the-slab / Slab Arena | `RestBench` | (17.6, 54.6) | 1 | 免费 |  |  |
| Slab_16 | the-slab / Slab Arena | `RestBench (1)` | (66.0, 18.6) | 1 | 免费 |  |  |
| Slab_20 | the-slab / Slab Grindle | `RestBench` | (35.8, 8.6) | 1 | 免费 |  |  |
| Under_01b | underworks / Broken Elevator | `…ormal World/Understore Toll Bench (1)/RestBench` | (29.9, 1.0) | 1101 | 付费 | 15（Understore Toll Bench Default） | 每次坐都要付（FSM `Behaviour (special)`，起身后翻回收费状态，无持久化） |
| Under_01b | underworks / Broken Elevator | `Understore Toll Bench/RestBench` | (18.4, 3.8) | 11 | 付费 | 15（Understore Toll Bench Default） | 每次坐都要付（FSM `Behaviour (special)`，起身后翻回收费状态，无持久化） |
| Under_08 | underworks / Confession Toll | `Understore Toll Bench (1)/RestBench (1)` | (83.4, 16.7) | 11 | 付费 | 15（Understore Toll Bench Default） | 每次坐都要付（FSM `Behaviour (special)`，无持久化） |
| Under_08 | underworks / Confession Toll | `Understore Toll Bench (2)/RestBench (2)` | (87.4, 16.7) | 11 | 付费 | 15（Understore Toll Bench Default） | 每次坐都要付（FSM `Behaviour (special)`，无持久化） |
| Under_08 | underworks / Confession Toll | `Understore Toll Bench/RestBench` | (79.4, 16.7) | 11 | 付费 | 15（Understore Toll Bench Default） | 每次坐都要付（FSM `Behaviour (special)`，无持久化） |
| Under_17 | underworks / Underworks Twelfth Architect | `RestBench` | (36.5, 13.7) | 1 | 免费 |  |  |
| Weave_07 | weavenest-atla / Weavenest Atla Bench | `RestBench` | (30.9, 105.7) | 1 | 免费 |  |  |
| Wisp_04 | whisp-thicket / Wisp Thicket Bench | `Fall Bench Group/RestBench` | (57.8, 14.8) | 11 | 有条件 |  | `Fall Bench Group` 的 FSM `Bench Fall Control`（未展开） |
| Library_08 | whispering-vaults / Whispering Vaults Bench | `RestBench` | (26.1, 24.6) | 1 | 免费 |  |  |
| Library_10 | whispering-vaults / Vaultkeeper Cauldron Entrance | `RestBench` | (101.1, 4.7) | 1 | 免费 |  |  |
| Ward_01 | whiteward / Whiteward Entrance | `RestBench` | (60.0, 97.5) | 1 | 免费 |  |  |
| Crawl_08 | wormways / Wormways Laboratory | `RestBench` | (41.2, 7.8) | 1 | 免费 |  |  |
